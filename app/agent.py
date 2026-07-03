# ruff: noqa
import datetime
import os
from zoneinfo import ZoneInfo
from typing import AsyncGenerator

from google.adk.workflow import Workflow, START
from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.adk.tools import AgentTool
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.genai import types
from pydantic import BaseModel, Field

# MCP Imports
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from .config import config

# -----------------------------------------------------------------------------
# 0. MCP Toolset Setup
# -----------------------------------------------------------------------------

# Configure connection to the local MCP server running over stdio
mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uv",
            args=["run", "app/mcp_server.py"],
        ),
    ),
)

# -----------------------------------------------------------------------------
# 1. State & Output Schemas
# -----------------------------------------------------------------------------

class FarmerProfile(BaseModel):
    language: str = "English"
    location: str = "Unknown"
    crops: list[str] = []
    farm_size: str = "Unknown"

class WorkflowState(BaseModel):
    farmer_profile: FarmerProfile = FarmerProfile()
    user_query: str = ""
    audit_log: list[dict] = []

class OrchestratorOutput(BaseModel):
    response: str = Field(
        description="The final farming advice or the response compiled from the sub-agents."
    )
    needs_more_info: bool = Field(
        description="True if we need to ask the farmer for missing profile details (e.g., location/state, crop type, or land size) to answer their query."
    )
    info_request_message: str = Field(
        description="The friendly question to ask the farmer if needs_more_info is True."
    )

# -----------------------------------------------------------------------------
# 2. Specialized LLM Agents (Sub-Agents)
# -----------------------------------------------------------------------------

farming_advisor = LlmAgent(
    name="farming_advisor",
    model=Gemini(model=config.model),
    instruction=(
        "You are BharatSahayak's Farming Advisor. Your goal is to help Indian farmers with agricultural queries. "
        "Use the calculate_farming_profitability tool to estimate and calculate farming costs and net profits when acreage is provided. "
        "Provide crop suggestions, farming methods, advice on soil preparation, and guidance for beginners. "
        "Translate agricultural knowledge into simple, easy-to-understand terms. Keep answers concise."
    ),
    tools=[mcp_toolset]
)

weather_advisor = LlmAgent(
    name="weather_advisor",
    model=Gemini(model=config.model),
    instruction=(
        "You are BharatSahayak's Weather Advisor. Use the get_weather_advisory tool to fetch weather forecasts and tailored agricultural tips. "
        "Give advice on irrigation schedules, rain warnings, and temperature effects on specific crops. "
        "Keep answers practical and focus on what actions the farmer should take."
    ),
    tools=[mcp_toolset]
)

gov_schemes_advisor = LlmAgent(
    name="gov_schemes_advisor",
    model=Gemini(model=config.model),
    instruction=(
        "You are BharatSahayak's Government Schemes Advisor. Use the search_government_schemes tool to look up local/national agricultural programs and subsidies. "
        "Help farmers discover central and state government schemes, subsidies, and eligibility rules. Detail document checklists and application guides in simple language."
    ),
    tools=[mcp_toolset]
)

crop_disease_advisor = LlmAgent(
    name="crop_disease_advisor",
    model=Gemini(model=config.model),
    instruction=(
        "You are BharatSahayak's Crop Disease Advisor. Use the get_crop_disease_info tool to diagnose crop diseases and identify cures based on symptoms. "
        "Identify crop diseases and suggest treatments. Provide preventative tips. Since the farmer might provide a crop name or symptom, explain issues in simple terms."
    ),
    tools=[mcp_toolset]
)


# -----------------------------------------------------------------------------
# 3. Orchestrator LLM Agent
# -----------------------------------------------------------------------------

orchestrator = LlmAgent(
    name="orchestrator",
    model=Gemini(model=config.model),
    instruction=(
        "You are BharatSahayak's primary Orchestrator. "
        "Your task is to analyze the user's input/query, check the farmer's profile, and delegate the query to the correct advisor using tools. "
        "If you need missing information to answer the query (e.g. the farmer's state or farm size), set needs_more_info to True and write a helpful prompt in info_request_message. "
        "Otherwise, use the appropriate sub-agent tool to get the answer, and then provide a comprehensive response."
    ),
    tools=[
        AgentTool(farming_advisor),
        AgentTool(weather_advisor),
        AgentTool(gov_schemes_advisor),
        AgentTool(crop_disease_advisor)
    ],
    output_schema=OrchestratorOutput
)

# -----------------------------------------------------------------------------
# 4. Workflow Nodes (Python functions)
# -----------------------------------------------------------------------------

def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    """Security Checkpoint Node - PII scrubbing, prompt injection detection, and content safety."""
    import re
    import sys
    import json
    
    text_query = ""
    if node_input and node_input.parts:
        text_query = "".join(part.text for part in node_input.parts if part.text)
        
    # Initialize audit logs list in state
    if "audit_log" not in ctx.state:
        ctx.state["audit_log"] = []
        
    audit_entry = {
        "timestamp": datetime.datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
        "input_length": len(text_query),
        "severity": "INFO",
        "action": "PASS",
        "details": "Input query passed security checks."
    }
    
    # 1. PII Scrubbing (Aadhaar number, mobile, email)
    aadhaar_pattern = r"\b\d{4}\s\d{4}\s\d{4}\b|\b\d{12}\b"
    mobile_pattern = r"\b[6-9]\d{9}\b"
    email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    
    scrubbed = False
    if re.search(aadhaar_pattern, text_query):
        text_query = re.sub(aadhaar_pattern, "[AADHAAR_REDACTED]", text_query)
        scrubbed = True
    if re.search(mobile_pattern, text_query):
        text_query = re.sub(mobile_pattern, "[PHONE_REDACTED]", text_query)
        scrubbed = True
    if re.search(email_pattern, text_query):
        text_query = re.sub(email_pattern, "[EMAIL_REDACTED]", text_query)
        scrubbed = True
        
    if scrubbed:
        audit_entry["action"] = "SCRUBBED"
        audit_entry["severity"] = "WARNING"
        audit_entry["details"] = "PII (Aadhaar/Mobile/Email) detected and redacted."
        
    # 2. Prompt Injection Detection
    injection_keywords = [
        "system prompt", "ignore previous instructions", "bypass rules", 
        "override instructions", "developer mode", "jailbreak", "prompt injection"
    ]
    
    injected = False
    for kw in injection_keywords:
        if kw in text_query.lower():
            injected = True
            break
            
    if injected:
        audit_entry["action"] = "BLOCKED_INJECTION"
        audit_entry["severity"] = "CRITICAL"
        audit_entry["details"] = "Prompt injection attempt detected."
        ctx.state["audit_log"].append(audit_entry)
        print(f"[SECURITY ALERT] {json.dumps(audit_entry)}", file=sys.stderr)
        
        rejection_msg = "Security Alert: Prompt injection or instruction override attempt detected. Action blocked."
        return Event(output=rejection_msg, route="security_breach")
        
    # 3. Domain-Specific Content & Financial Safety Rule
    financial_keywords = [
        "bank pin", "atm pin", "netbanking password", "credit card", "cvv"
    ]
    harmful_farming_keywords = [
        "how to poison crops", "how to sabotage soil", "make explosives"
    ]
    
    unsafe = False
    for kw in financial_keywords + harmful_farming_keywords:
        if kw in text_query.lower():
            unsafe = True
            break
            
    if unsafe:
        audit_entry["action"] = "BLOCKED_UNSAFE"
        audit_entry["severity"] = "CRITICAL"
        audit_entry["details"] = "Unsafe query containing sensitive financial requests or harmful agricultural sabotage."
        ctx.state["audit_log"].append(audit_entry)
        print(f"[SECURITY ALERT] {json.dumps(audit_entry)}", file=sys.stderr)
        
        rejection_msg = "Security Alert: Your query contains sensitive financial requests or off-topic unsafe instructions. Action blocked."
        return Event(output=rejection_msg, route="security_breach")
        
    # Log successful check
    ctx.state["audit_log"].append(audit_entry)
    print(f"[SECURITY AUDIT] {json.dumps(audit_entry)}", file=sys.stderr)
    
    if scrubbed:
        scrubbed_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=text_query)]
        )
        return Event(output=scrubbed_content)
        
    return Event(output=node_input)

def load_farmer_profile(ctx: Context, node_input: types.Content) -> Event:
    """Loads and updates the farmer profile based on conversation input."""
    text_query = ""
    if node_input and node_input.parts:
        text_query = "".join(part.text for part in node_input.parts if part.text)
    
    ctx.state["user_query"] = text_query
    
    if "farmer_profile" not in ctx.state:
        ctx.state["farmer_profile"] = {
            "language": "English",
            "location": "Unknown",
            "crops": [],
            "farm_size": "Unknown"
        }
    
    profile = ctx.state["farmer_profile"]
    q_lower = text_query.lower()
    
    # Basic rule-based memory updates
    if "punjab" in q_lower:
        profile["location"] = "Punjab"
    elif "karnataka" in q_lower:
        profile["location"] = "Karnataka"
    elif "haryana" in q_lower:
        profile["location"] = "Haryana"
        
    if "wheat" in q_lower:
        if "wheat" not in profile["crops"]:
            profile["crops"].append("wheat")
    if "rice" in q_lower:
        if "rice" not in profile["crops"]:
            profile["crops"].append("rice")
    if "cotton" in q_lower:
        if "cotton" not in profile["crops"]:
            profile["crops"].append("cotton")
            
    if "acre" in q_lower:
        import re
        match = re.search(r"(\d+)\s*acres?", q_lower)
        if match:
            profile["farm_size"] = f"{match.group(1)} acres"
            
    orchestrator_prompt = (
        f"Farmer Profile:\n"
        f"- Location: {profile['location']}\n"
        f"- Crops: {', '.join(profile['crops']) if profile['crops'] else 'None declared'}\n"
        f"- Farm Size: {profile['farm_size']}\n"
        f"- Language: {profile['language']}\n\n"
        f"User Query: {text_query}"
    )
    
    return Event(output=orchestrator_prompt, state={"farmer_profile": profile})

async def hitl_checkpoint(ctx: Context, node_input: dict) -> Event | AsyncGenerator:
    """Handles Human-in-the-Loop inputs if the orchestrator requests it."""
    needs_more_info = node_input.get("needs_more_info", False)
    info_request_message = node_input.get("info_request_message", "")
    response = node_input.get("response", "")
    
    if needs_more_info:
        if not ctx.resume_inputs or "more_info" not in ctx.resume_inputs:
            yield RequestInput(interrupt_id="more_info", message=info_request_message)
            return
        
        user_answer = ctx.resume_inputs["more_info"]
        original_query = ctx.state.get("user_query", "")
        updated_query = f"{original_query} (Additional farmer response: {user_answer})"
        ctx.state["user_query"] = updated_query
        
        profile = ctx.state.get("farmer_profile", {})
        ua_lower = user_answer.lower()
        
        if "punjab" in ua_lower:
            profile["location"] = "Punjab"
        elif "karnataka" in ua_lower:
            profile["location"] = "Karnataka"
        elif "haryana" in ua_lower:
            profile["location"] = "Haryana"
            
        import re
        match = re.search(r"(\d+)\s*acres?", ua_lower)
        if match:
            profile["farm_size"] = f"{match.group(1)} acres"
            
        orchestrator_prompt = (
            f"Farmer Profile:\n"
            f"- Location: {profile.get('location', 'Unknown')}\n"
            f"- Crops: {', '.join(profile.get('crops', [])) if profile.get('crops') else 'None declared'}\n"
            f"- Farm Size: {profile.get('farm_size', 'Unknown')}\n"
            f"- Language: {profile.get('language', 'English')}\n\n"
            f"User Query: {updated_query}"
        )
        
        yield Event(output=orchestrator_prompt, route="retry_with_info", state={"farmer_profile": profile, "user_query": updated_query})
        return
        
    yield Event(output=response)

def format_final_output(node_input: str) -> Event:
    """Format and stream output to the UI."""
    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=node_input)]
        )
    )
    yield Event(output=node_input)

# -----------------------------------------------------------------------------
# 5. Workflow Definitions
# -----------------------------------------------------------------------------

root_agent = Workflow(
    name="bharatsahayak_workflow",
    edges=[
        (START, security_checkpoint),
        (security_checkpoint, {
            "__DEFAULT__": load_farmer_profile,
            "security_breach": format_final_output
        }),
        (load_farmer_profile, orchestrator),
        (orchestrator, hitl_checkpoint),
        (hitl_checkpoint, {
            "__DEFAULT__": format_final_output,
            "retry_with_info": orchestrator
        })
    ],
    description="BharatSahayak AI Farming Companion Workflow"
)

app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(enabled=True)
)
