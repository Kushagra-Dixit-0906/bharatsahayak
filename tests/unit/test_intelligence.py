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
    
    from app.agent import hitl_checkpoint
    events = []
    async for event in hitl_checkpoint(ctx, node_input):
        events.append(event)
        
    assert len(events) == 1
    
    # Check state updates
    profile = ctx.state["farmer_profile"]
    assert "paddy" in profile["crops"]
    assert profile["location"] == "Punjab"
    assert profile["farm_size"] == "5 acres"
    
    # Verify that the input has been popped to prevent loops
    assert "more_info" not in ctx.resume_inputs

