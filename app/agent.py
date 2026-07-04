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
        default="",
        description="The final farming advice or the response compiled from the sub-agents."
    )
    needs_more_info: bool = Field(
        default=False,
        description="True if we need to ask the farmer for missing profile details (e.g., location/state, crop type, or land size) to answer their query."
    )
    info_request_message: str = Field(
        default="",
        description="The friendly question to ask the farmer if needs_more_info is True."
    )

# -----------------------------------------------------------------------------
# 2. Specialized LLM Agents (Sub-Agents)
# -----------------------------------------------------------------------------

farming_advisor = LlmAgent(
    name="farming_advisor",
    model=Gemini(model=config.model),
    instruction=(
        "You are BharatSahayak's Farming Advisor. Your goal is to help Indian farmers with agricultural queries.\n"
        "Follow these rules when formulating your response:\n"
        "1. Provide region (state/district) and season-specific crop recommendations.\n"
        "2. When recommending a crop, you MUST mention the following 7 details in a concise, structured, and farmer-friendly format:\n"
        "   - Why the crop was chosen (e.g., suitability to region, soil, or climate)\n"
        "   - Investment per acre (estimated cultivation cost per acre)\n"
        "   - Expected profit (net profit or expected profit range)\n"
        "   - Difficulty level (e.g., Easy, Moderate, Hard)\n"
        "   - Best sowing season\n"
        "   - One government scheme that may help (e.g., PM-KISAN, PMFBY, Krishi Bhagya, etc. Search for schemes using search_government_schemes if needed)\n"
        "   - Next practical steps (e.g., soil test, buying seeds, sowing)\n"
        "3. Suggest crop varieties suitable for the region/season and identify selling opportunities (e.g., local mandis, e-NAM, processors).\n"
        "4. If acreage/farm size is provided in the input or query, you MUST always call the `calculate_farming_profitability` tool to estimate and calculate farming costs and net profits.\n"
        "5. If the user is new to farming or a beginner, provide beginner-friendly crop recommendations along with a step-by-step farming plan (soil preparation, sowing, irrigation, harvesting).\n"
        "6. If the user asks about or refers to another state or location in their query, prioritize and answer for that location/state instead of assuming or requesting the saved profile location.\n"
        "7. Respond in the same language as the user whenever possible (e.g., Hindi, Kannada, Telugu, etc.). When responding in Hindi or other languages, you MUST preserve all 7 required sections in the same order and translate their headings accurately (e.g., in Hindi: 1. यह फसल क्यों, 2. प्रति एकड़ निवेश, 3. अपेक्षित लाभ, 4. कठिनाई स्तर, 5. बुवाई का सबसे अच्छा मौसम, 6. सरकारी योजना, 7. अगले व्यावहारिक कदम). Do not omit or merge any section.\n"
        "Keep answers simple, easy to understand, and concise."
    ),
    tools=[mcp_toolset]
)

weather_advisor = LlmAgent(
    name="weather_advisor",
    model=Gemini(model=config.model),
    instruction=(
        "You are BharatSahayak's Weather Advisor. Follow these rules when formulating your response:\n"
        "1. Always call the `get_weather_advisory` tool to fetch weather forecasts and tailored agricultural tips.\n"
        "2. Your response must include specific irrigation advice, fertilizer advice (e.g., urea application timing), disease risk warnings (e.g., rust or blast), and clear next actions for the farmer.\n"
        "3. Respond in the same language as the user (e.g., Hindi, Kannada, Telugu, etc.).\n"
        "Keep answers practical and focus on what actions the farmer should take."
    ),
    tools=[mcp_toolset]
)

gov_schemes_advisor = LlmAgent(
    name="gov_schemes_advisor",
    model=Gemini(model=config.model),
    instruction=(
        "You are BharatSahayak's Government Schemes Advisor. Follow these rules when formulating your response:\n"
        "1. Always use the `search_government_schemes` tool to look up local/national agricultural programs and subsidies.\n"
        "2. For each relevant scheme, make sure to detail: eligibility criteria, required documents, benefits (subsidies/income support), and the step-by-step application process.\n"
        "3. Respond in the same language as the user (e.g., Hindi, Kannada, Telugu, etc.).\n"
        "Translate agricultural schemes into simple, easy-to-understand terms."
    ),
    tools=[mcp_toolset]
)

crop_disease_advisor = LlmAgent(
    name="crop_disease_advisor",
    model=Gemini(model=config.model),
    instruction=(
        "You are BharatSahayak's Crop Disease Advisor. Follow these rules when formulating your response:\n"
        "1. Always use the `get_crop_disease_info` tool to diagnose crop diseases and identify cures based on symptoms.\n"
        "2. Your response must include: disease severity level, potential causes, treatment options (chemical and organic, if available), prevention tips, and a clear guideline on when they should contact a local agricultural expert.\n"
        "3. Respond in the same language as the user (e.g., Hindi, Kannada, Telugu, etc.).\n"
        "Explain symptoms and remedies in simple, jargon-free terms."
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
        "You are BharatSahayak's primary Orchestrator.\n"
        "Your task is to analyze the user's input/query, check the farmer's profile, and delegate the query to the correct advisor using tools.\n"
        "If you need missing information to answer the query (e.g. the farmer's state or farm size), set needs_more_info to True and write a helpful prompt in info_request_message.\n"
        "However, if the user specifies or asks about another state or location in their query, prioritize that location for tool calling and response instead of asking for or assuming the saved profile location.\n"
        "Ensure that both the final response and the info_request_message are in the same language as the user whenever possible (e.g., Hindi, Kannada, Telugu, etc.).\n"
        "You MUST respond ONLY with a valid JSON object conforming to the OrchestratorOutput schema. Do not include any conversational preamble or wrap the JSON in markdown code blocks."
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

def extract_location(text: str) -> str | None:
    text_lower = text.lower()
    state_mapping = {
        "punjab": "Punjab",
        "karnataka": "Karnataka",
        "haryana": "Haryana",
        "maharashtra": "Maharashtra",
        "gujarat": "Gujarat",
        "rajasthan": "Rajasthan",
        "tamil nadu": "Tamil Nadu",
        "andhra pradesh": "Andhra Pradesh",
        "telangana": "Telangana",
        "uttar pradesh": "Uttar Pradesh",
        "madhya pradesh": "Madhya Pradesh",
        "bihar": "Bihar",
        "west bengal": "West Bengal",
        "odisha": "Odisha",
        "kerala": "Kerala",
        "assam": "Assam",
        "himachal pradesh": "Himachal Pradesh",
        "uttarakhand": "Uttarakhand",
        "chhattisgarh": "Chhattisgarh",
        "jharkhand": "Jharkhand",
        "bangalore": "Karnataka",
        "bengaluru": "Karnataka",
        "mumbai": "Maharashtra",
        "pune": "Maharashtra",
        "nagpur": "Maharashtra",
        "hyderabad": "Telangana",
        "chennai": "Tamil Nadu",
        "jaipur": "Rajasthan",
        "lucknow": "Uttar Pradesh",
        "patna": "Bihar",
        "kolkata": "West Bengal",
        "bhopal": "Madhya Pradesh",
        "ahmedabad": "Gujarat"
    }
    for key, val in state_mapping.items():
        if key in text_lower:
            return val
            
    words = text.strip().split()
    words_lower = [w.lower() for w in words]
    if len(words) <= 2 and not any(w in words_lower for w in ["i", "am", "in", "from", "live", "my", "is"]):
        cleaned = "".join(c for c in text if c.isalnum() or c.isspace()).strip()
        if cleaned:
            return cleaned.title()
            
    import re
    match = re.search(r"\b(?:in|from|at)\s+([A-Za-z]+)", text)
    if match:
        loc = match.group(1).strip()
        if loc.lower() not in ["the", "my", "a", "an", "this", "some"]:
            return loc.capitalize()
    return None

def extract_crops(text: str, current_crops: list[str]) -> list[str]:
    text_lower = text.lower()
    supported_crops = [
        "wheat", "rice", "cotton", "potato", "tomato", "maize",
        "sugarcane", "mustard", "onion", "soybean", "paddy", "vegetables"
    ]
    updated_crops = list(current_crops)
    for crop in supported_crops:
        if crop in text_lower:
            if crop not in updated_crops:
                updated_crops.append(crop)
    return updated_crops

def extract_farm_size(text: str) -> str | None:
    import re
    text_lower = text.lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*acres?", text_lower)
    if match:
        return f"{match.group(1)} acres"
    return None

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
    
    loc = extract_location(text_query)
    if loc:
        profile["location"] = loc
        
    profile["crops"] = extract_crops(text_query, profile["crops"])
    
    sz = extract_farm_size(text_query)
    if sz:
        profile["farm_size"] = sz
            
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
        
        user_answer = ctx.resume_inputs.pop("more_info")
        original_query = ctx.state.get("user_query", "")
        updated_query = f"{original_query} (Additional farmer response: {user_answer})"
        ctx.state["user_query"] = updated_query
        
        profile = ctx.state.get("farmer_profile", {})
        
        loc = extract_location(user_answer)
        if loc:
            profile["location"] = loc
            
        profile["crops"] = extract_crops(user_answer, profile.get("crops", []))
        
        sz = extract_farm_size(user_answer)
        if sz:
            profile["farm_size"] = sz
            
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
