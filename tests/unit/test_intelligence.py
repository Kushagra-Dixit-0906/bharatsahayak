from google.genai import types
from app.agent import load_farmer_profile, OrchestratorOutput

class MockContext:
    def __init__(self):
        self.state = {}

def test_orchestrator_output_defaults() -> None:
    """Test that OrchestratorOutput defaults are set correctly."""
    output = OrchestratorOutput()
    assert output.response == ""
    assert output.needs_more_info is False
    assert output.info_request_message == ""

def test_load_farmer_profile_crops() -> None:
    """Test that load_farmer_profile detects new crop types and updates profile correctly."""
    # Create empty context
    ctx = MockContext()
    
    # Simulate user query mentioning crops and location
    node_input = types.Content(
        role="user",
        parts=[types.Part.from_text(text="I want to grow potato, tomato, and sugarcane in Karnataka.")]
    )
    
    # Run the load_farmer_profile node function
    event = load_farmer_profile(ctx, node_input)
    
    # Check that state is updated correctly
    profile = ctx.state["farmer_profile"]
    assert "potato" in profile["crops"]
    assert "tomato" in profile["crops"]
    assert "sugarcane" in profile["crops"]
    assert profile["location"] == "Karnataka"
    
    # Check that standard crop works as well
    assert "wheat" not in profile["crops"]

def test_location_extractions() -> None:
    """Test location extraction helper with various inputs."""
    from app.agent import extract_location
    assert extract_location("I am in pune") == "Maharashtra"
    assert extract_location("Indore") == "Indore"
    assert extract_location("from Bangalore") == "Karnataka"
    assert extract_location("in Gujarat") == "Gujarat"
    assert extract_location("None of the above") is None

import pytest

@pytest.mark.asyncio
async def test_hitl_checkpoint_consumption() -> None:
    """Test that hitl_checkpoint pops more_info and extracts all profile details."""
    ctx = MockContext()
    ctx.state["user_query"] = "I need help"
    ctx.state["farmer_profile"] = {"crops": [], "location": "Unknown", "farm_size": "Unknown"}
    ctx.resume_inputs = {"more_info": "paddy in Punjab on 5 acres"}
    
    node_input = {"needs_more_info": True, "info_request_message": "Please specify", "response": ""}
    
    from app.agent import _hitl_checkpoint_impl
    events = []
    async for event in _hitl_checkpoint_impl(ctx, node_input):
        events.append(event)
        
    assert len(events) == 1
    
    # Check state updates
    profile = ctx.state["farmer_profile"]
    assert "paddy" in profile["crops"]
    assert profile["location"] == "Punjab"
    assert profile["farm_size"] == "5 acres"
    
    # Verify that the input has been popped to prevent loops
    assert "more_info" not in ctx.resume_inputs


@pytest.mark.asyncio
async def test_hitl_checkpoint_intercepts_missing_season() -> None:
    """Test that hitl_checkpoint intercepts queries missing a season."""
    ctx = MockContext()
    ctx.state["user_query"] = "I have 2 acres in Uttar Pradesh and want to start farming."
    ctx.state["farmer_profile"] = {"crops": [], "location": "Uttar Pradesh", "farm_size": "2 acres"}
    ctx.resume_inputs = {}
    
    node_input = {
        "needs_more_info": False,
        "info_request_message": "",
        "response": "🌱 Recommended Crop: Wheat ..."
    }
    
    from app.agent import _hitl_checkpoint_impl
    from google.adk.events.request_input import RequestInput
    
    events = []
    async for event in _hitl_checkpoint_impl(ctx, node_input):
        events.append(event)
        
    assert len(events) == 1
    assert isinstance(events[0], RequestInput)
    assert events[0].interrupt_id == "more_info"
    assert events[0].message == "To recommend the best crop, please tell me which season you are planning to farm in: Kharif, Rabi, or Zaid."


@pytest.mark.asyncio
async def test_hitl_checkpoint_multilingual_season_clarification_hindi() -> None:
    """Test that hitl_checkpoint uses Hindi clarification prompt for Hindi queries."""
    ctx = MockContext()
    ctx.state["user_query"] = "मेरे पास उत्तर प्रदेश में 2 एकड़ जमीन है और मैं खेती शुरू करना चाहता हूं।"
    ctx.state["farmer_profile"] = {"crops": [], "location": "Uttar Pradesh", "farm_size": "2 acres", "language": "English"}
    ctx.resume_inputs = {}
    
    node_input = {
        "needs_more_info": False,
        "info_request_message": "",
        "response": "अनुशंसित फसल..."
    }
    
    from app.agent import _hitl_checkpoint_impl
    from google.adk.events.request_input import RequestInput
    
    events = []
    async for event in _hitl_checkpoint_impl(ctx, node_input):
        events.append(event)
        
    assert len(events) == 1
    assert isinstance(events[0], RequestInput)
    assert events[0].interrupt_id == "more_info"
    assert "🌾 सर्वोत्तम फसल की सिफारिश करने के लिए कृपया बताइए कि आप किस मौसम में खेती करना चाहते हैं" in events[0].message
    assert "• खरीफ" in events[0].message
    assert "• रबी" in events[0].message
    assert "• ज़ायद" in events[0].message


@pytest.mark.asyncio
async def test_hitl_checkpoint_season_only_reply_preserves_location() -> None:
    """Test that a season-only reply updates season but does not overwrite location."""
    ctx = MockContext()
    ctx.state["user_query"] = "I need crop recommendations"
    ctx.state["farmer_profile"] = {
        "crops": [],
        "location": "Uttar Pradesh",
        "farm_size": "2 acres",
        "language": "English",
        "season": None
    }
    ctx.resume_inputs = {"more_info": "Kharif"}
    
    node_input = {
        "needs_more_info": True,
        "info_request_message": "Please specify season",
        "response": ""
    }
    
    from app.agent import _hitl_checkpoint_impl
    events = []
    async for event in _hitl_checkpoint_impl(ctx, node_input):
        events.append(event)
        
    assert len(events) == 1
    profile = ctx.state["farmer_profile"]
    assert profile["location"] == "Uttar Pradesh"
    assert profile["season"] == "Kharif"


def test_orchestrator_output_validation_dict() -> None:
    """Test that OrchestratorOutput's custom response field_validator correctly formats dictionary responses."""
    data = {
        "response": {"request": "मैं उत्तर प्रदेश में नया किसान हूँ। मुझे कौन सी फसल उगानी चाहिए?"},
        "needs_more_info": False,
        "info_request_message": ""
    }
    output = OrchestratorOutput.model_validate(data)
    assert output.response == "मैं उत्तर प्रदेश में नया किसान हूँ। मुझे कौन सी फसल उगानी चाहिए?"


