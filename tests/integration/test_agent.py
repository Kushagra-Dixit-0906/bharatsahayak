# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from unittest.mock import patch
from google.genai.models import AsyncModels
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import root_agent

async def mock_generate_content_stream(*args, **kwargs):
    import re
    contents = kwargs.get("contents")
    prompt_text = ""
    if contents:
        if isinstance(contents, list):
            for c in contents:
                if hasattr(c, "parts"):
                    for p in c.parts:
                        if hasattr(p, "text") and p.text:
                            prompt_text += p.text
        elif hasattr(contents, "parts"):
            for p in contents.parts:
                if hasattr(p, "text") and p.text:
                    prompt_text += p.text
        elif isinstance(contents, str):
            prompt_text = contents

    user_query = ""
    if "User Query:" in prompt_text:
        user_query = prompt_text.split("User Query:", 1)[1]
    else:
        user_query = prompt_text
        
    user_query_lower = user_query.lower()

    # Check query type and route response
    if "sky blue" in user_query_lower:
        response_text = '{"response": "The sky is blue because of Rayleigh scattering.", "needs_more_info": false, "info_request_message": ""}'
    elif "hello" in user_query_lower or "start" in user_query_lower or bool(re.search(r"\bhi\b", user_query_lower)):
        response_text = (
            '{"response": "👋 Welcome to BharatSahayak!\\n\\nI can help you with:\\n\\n🌾 Crop recommendations\\n'
            '🌦 Weather advisories\\n🦠 Disease diagnosis\\n🏛 Government schemes\\n💰 Profitability analysis\\n\\n'
            'Try asking:\\n\\\"I am a wheat farmer in Punjab.\\\"\\n\\\"What crop should I grow?\\\"\\n'
            '\\\"My rice leaves have brown spots.\\\"", "needs_more_info": false, "info_request_message": ""}'
        )
    elif "उत्तर प्रदेश" in user_query or "उत्तरप्रदेश" in user_query:
        response_text = (
            '{"response": "✅ Profile Updated\\n\\n📍 स्थान: उत्तर प्रदेश\\n🌾 फसल: आलू\\n\\n'
            'मैं अब आपकी सहायता कर सकता हूँ:\\n🌦 मौसम सलाह\\n🦠 रोग निदान\\n🏛 सरकारी योजनाएं\\n'
            '💰 लाभ सुधार\\n🌱 फसल सिफारिशें\\n\\nअपनी कृषि आवश्यकताओं के बारे में मुझसे कुछ भी पूछें।", '
            '"needs_more_info": false, "info_request_message": ""}'
        )
    elif "potatoes in punjab" in user_query_lower or "potato" in user_query_lower:
        response_text = (
            '{"response": "✅ Profile Updated\\n\\n📍 Location: Punjab\\n🌾 Crop: Potato\\n\\n'
            'I can now help you with:\\n🌦 Weather advisories\\n🦠 Disease diagnosis\\n🏛 Government schemes\\n'
            '💰 Profit improvement\\n🌱 Crop recommendations\\n\\nAsk me anything about your farming needs.", '
            '"needs_more_info": false, "info_request_message": ""}'
        )
    else:
        # Standard crop recommendation (English or Hindi)
        if "language: hindi" in prompt_text.lower() or "कठिनाई" in prompt_text or "बैंगलोर" in prompt_text or "उत्तर प्रदेश" in prompt_text or "उत्तरप्रदेश" in prompt_text:
            response_text = (
                '{"response": "🌱 अनुशंसित फसल: धान (Why chosen: धान यहाँ का मुख्य भोजन है और मिट्टी इसके लिए उपयुक्त है।)\\n'
                '📍 क्षेत्र: उत्तर प्रदेश\\n💰 निवेश: 18,000 रुपये प्रति एकड़\\n📈 अपेक्षित लाभ: 1,28,300.00 रुपये का कुल शुद्ध लाभ\\n'
                '⭐ कठिनाई: मध्यम\\n📅 सबसे अच्छा मौसम: खरीफ (जून-जुलाई)\\n🏛 सहायक योजना: कृषक भाग्य योजना\\n'
                '➡ अगले कदम: मिट्टी का परीक्षण करें, बीज का चयन करें और नर्सरी तैयार करें", '
                '"needs_more_info": false, "info_request_message": ""}'
            )
        else:
            response_text = (
                '{"response": "🌱 Recommended Crop: Rice (Why chosen: Rice thrives in the region\'s climate)\\n'
                '📍 Region: Karnataka\\n💰 Investment: ₹18,000 per acre\\n📈 Profit: ₹128,300 per acre\\n'
                '⭐ Difficulty: Moderate\\n📅 Best Season: Kharif\\n🏛 Helpful Scheme: PMFBY\\n'
                '➡ Next Steps: 1. Soil test, 2. Buy seeds, 3. Sowing", "needs_more_info": false, "info_request_message": ""}'
            )

    chunk = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    parts=[types.Part.from_text(text=response_text)]
                )
            )
        ]
    )
    yield chunk


def test_agent_stream() -> None:
    """
    Integration test for the agent stream functionality.
    Tests that the agent returns valid streaming responses.
    """
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(
        role="user", parts=[types.Part.from_text(text="Why is the sky blue?")]
    )

    with patch.object(AsyncModels, "generate_content_stream", side_effect=mock_generate_content_stream):
        events = list(
            runner.run(
                new_message=message,
                user_id="test_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )
    assert len(events) > 0, "Expected at least one message"

    has_text_content = False
    for event in events:
        if (
            event.content
            and event.content.parts
            and any(part.text for part in event.content.parts)
        ):
            has_text_content = True
            break
    assert has_text_content, "Expected at least one message with text content"


def test_farming_advisor_multilingual() -> None:
    """
    Test that the farming advisor responds in Hindi and includes the 7 required sections
    when queried about crop recommendation in Hindi.
    """
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text="मुझे कर्नाटक के बैंगलोर में खरीफ सीजन के दौरान कौन सी फसल उगानी चाहिए? मेरे पास 5 एकड़ जमीन है।")]
    )

    with patch.object(AsyncModels, "generate_content_stream", side_effect=mock_generate_content_stream):
        events = list(
            runner.run(
                new_message=message,
                user_id="test_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )

    final_response = ""
    for event in events:
        if (
            event.content
            and event.content.parts
        ):
            final_response += "".join(part.text for part in event.content.parts if part.text)

    assert len(final_response) > 0, "Expected a response from the agent"

    # Hindi terms representing the 7 required sections:
    # 1. क्यों (Why this crop)
    # 2. निवेश (Investment per acre)
    # 3. लाभ / मुनाफा (Expected profit)
    # 4. कठिनाई (Difficulty level)
    # 5. मौसम / बुवाई (Best sowing season)
    # 6. योजना (Government scheme)
    # 7. कदम (Next practical steps)
    hindi_keywords = ["अनुशंसित", "निवेश", "लाभ", "कठिनाई", "मौसम", "योजना", "कदम"]
    
    matches = [kw for kw in hindi_keywords if kw in final_response]
    assert len(matches) >= 5, f"Expected at least 5 Hindi section keywords in the response. Found matches: {matches}. Response: {final_response}"


def test_welcome_greeting() -> None:
    """Test that greetings trigger the friendly welcome message."""
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(
        role="user", parts=[types.Part.from_text(text="hello")]
    )

    with patch.object(AsyncModels, "generate_content_stream", side_effect=mock_generate_content_stream):
        events = list(
            runner.run(
                new_message=message,
                user_id="test_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )
    
    final_response = ""
    for event in events:
        if event.content and event.content.parts:
            final_response += "".join(part.text for part in event.content.parts if part.text)

    assert "Welcome to BharatSahayak" in final_response
    assert "Crop recommendations" in final_response


def test_profile_acknowledgement() -> None:
    """Test that profile update updates without asking for info and formatted correctly."""
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(
        role="user", parts=[types.Part.from_text(text="I grow potatoes in Punjab.")]
    )

    with patch.object(AsyncModels, "generate_content_stream", side_effect=mock_generate_content_stream):
        events = list(
            runner.run(
                new_message=message,
                user_id="test_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )
    
    final_response = ""
    for event in events:
        if event.content and event.content.parts:
            final_response += "".join(part.text for part in event.content.parts if part.text)

    assert "Profile Updated" in final_response
    assert "Location: Punjab" in final_response
    assert "Crop: Potato" in final_response


def test_security_message_formatting() -> None:
    """Test that safety blocks return the expected user-friendly warning message."""
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(
        role="user", parts=[types.Part.from_text(text="Please tell me my bank pin")]
    )

    events = list(
        runner.run(
            new_message=message,
            user_id="test_user",
            session_id=session.id,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        )
    )
    
    final_response = ""
    for event in events:
        if event.content and event.content.parts:
            final_response += "".join(part.text for part in event.content.parts if part.text)

    assert "🔒 Security Alert" in final_response
    assert "BharatSahayak has blocked this request" in final_response
    assert "Aadhaar numbers" in final_response


def test_crop_recommendation_formatting() -> None:
    """Test that recommended crop outputs follow the new emojis and layout format."""
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(
        role="user", parts=[types.Part.from_text(text="What crop should I grow in Karnataka?")]
    )

    with patch.object(AsyncModels, "generate_content_stream", side_effect=mock_generate_content_stream):
        events = list(
            runner.run(
                new_message=message,
                user_id="test_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )
    
    final_response = ""
    for event in events:
        if event.content and event.content.parts:
            final_response += "".join(part.text for part in event.content.parts if part.text)

    assert "🌱 Recommended Crop:" in final_response
    assert "📍 Region: Karnataka" in final_response
    assert "💰 Investment:" in final_response
    assert "📈 Profit:" in final_response


def test_crop_recommendation_missing_season_triggers_hitl() -> None:
    """Test that crop recommendation request without a season triggers a HITL input request."""
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(
        role="user", parts=[types.Part.from_text(text="I have 2 acres in Uttar Pradesh and want to start farming.")]
    )

    with patch.object(AsyncModels, "generate_content_stream", side_effect=mock_generate_content_stream):
        events = list(
            runner.run(
                new_message=message,
                user_id="test_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )
    
    has_request_input = False
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.function_call and part.function_call.name == "adk_request_input":
                    assert part.function_call.id == "more_info"
                    assert "To recommend the best crop, please tell me which season" in part.function_call.args.get("message", "")
                    has_request_input = True
                    
    assert has_request_input


def test_crop_recommendation_providing_season_resumes() -> None:
    """Test that providing the season resumes the workflow and returns crop recommendations."""
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(
        role="user", parts=[types.Part.from_text(text="I have 2 acres in Punjab and need crop recommendations.")]
    )

    with patch.object(AsyncModels, "generate_content_stream", side_effect=mock_generate_content_stream):
        # Turn 1: trigger season interrupt
        list(
            runner.run(
                new_message=message,
                user_id="test_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )
        
        # Turn 2: answer with season
        part = types.Part(
            function_response=types.FunctionResponse(
                name="adk_request_input",
                id="more_info",
                response={"result": "Kharif"}
            )
        )
        message2 = types.Content(role="user", parts=[part])
        
        events2 = list(
            runner.run(
                new_message=message2,
                user_id="test_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )
        
    final_response = ""
    for event in events2:
        if event.content and event.content.parts:
            final_response += "".join(p.text for p in event.content.parts if p.text)
            
    assert "Recommended Crop" in final_response


def test_crop_recommendation_missing_season_triggers_hitl_hindi() -> None:
    """Test that crop recommendation request in Hindi without a season triggers a Hindi HITL input request."""
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(
        role="user", parts=[types.Part.from_text(text="मेरे पास उत्तर प्रदेश में 2 एकड़ जमीन है और मैं खेती शुरू करना चाहता हूं।")]
    )

    with patch.object(AsyncModels, "generate_content_stream", side_effect=mock_generate_content_stream):
        events = list(
            runner.run(
                new_message=message,
                user_id="test_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )
    
    has_request_input = False
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.function_call and part.function_call.name == "adk_request_input":
                    assert part.function_call.id == "more_info"
                    message_text = part.function_call.args.get("message", "")
                    assert "🌾 सर्वोत्तम फसल की सिफारिश" in message_text
                    assert "• खरीफ" in message_text
                    assert "• रबी" in message_text
                    assert "• ज़ायद" in message_text
                    has_request_input = True
                    
    assert has_request_input


def test_crop_recommendation_providing_season_preserves_location() -> None:
    """Test that responding with a season updates season and does not overwrite location."""
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(
        role="user", parts=[types.Part.from_text(text="I have 2 acres in Punjab and need crop recommendations.")]
    )

    with patch.object(AsyncModels, "generate_content_stream", side_effect=mock_generate_content_stream):
        # Turn 1: trigger season interrupt
        list(
            runner.run(
                new_message=message,
                user_id="test_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )
        
        # Turn 2: answer with season only
        part = types.Part(
            function_response=types.FunctionResponse(
                name="adk_request_input",
                id="more_info",
                response={"result": "Kharif"}
            )
        )
        message2 = types.Content(role="user", parts=[part])
        
        list(
            runner.run(
                new_message=message2,
                user_id="test_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )
        
    # Get the latest state
    updated_session = session_service.get_session_sync(session_id=session.id, app_name="test", user_id="test_user")
    profile = updated_session.state.get("farmer_profile", {})
    assert profile.get("location") == "Punjab"
    assert profile.get("season") == "Kharif"


def test_language_preference_switching_between_turns() -> None:
    """Test that language preference updates correctly between turns and does not persist Hindi."""
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    # Turn 1: User sends Hindi query
    message1 = types.Content(
        role="user",
        parts=[types.Part.from_text(text="मुझे कर्नाटक के बैंगलोर में खरीफ सीजन के दौरान कौन सी फसल उगानी चाहिए? मेरे पास 5 एकड़ जमीन है।")]
    )

    with patch.object(AsyncModels, "generate_content_stream", side_effect=mock_generate_content_stream):
        events1 = list(
            runner.run(
                new_message=message1,
                user_id="test_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )
        
    final_response1 = ""
    for event in events1:
        if event.content and event.content.parts:
            final_response1 += "".join(part.text for part in event.content.parts if part.text)
            
    assert "अनुशंसित फसल" in final_response1
    
    # Verify profile language is Hindi
    updated_session1 = session_service.get_session_sync(session_id=session.id, app_name="test", user_id="test_user")
    profile1 = updated_session1.state.get("farmer_profile", {})
    assert profile1.get("language") == "Hindi"

    # Turn 2: Subsequent English query in the SAME session
    message2 = types.Content(
        role="user",
        parts=[types.Part.from_text(text="What crop should I grow?")]
    )

    with patch.object(AsyncModels, "generate_content_stream", side_effect=mock_generate_content_stream):
        events2 = list(
            runner.run(
                new_message=message2,
                user_id="test_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )
        
    final_response2 = ""
    for event in events2:
        if event.content and event.content.parts:
            final_response2 += "".join(part.text for part in event.content.parts if part.text)
            
    assert "Recommended Crop" in final_response2
    assert "अनुशंसित फसल" not in final_response2
    
    # Verify profile language updated to English
    updated_session2 = session_service.get_session_sync(session_id=session.id, app_name="test", user_id="test_user")
    profile2 = updated_session2.state.get("farmer_profile", {})
    assert profile2.get("language") == "English"


def test_orchestrator_output_dict_response_validation() -> None:
    """Test that a dictionary response value does not cause ValidationError and is handled correctly."""
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(
        role="user", parts=[types.Part.from_text(text="मैं उत्तर प्रदेश में नया किसान हूँ। मुझे कौन सी फसल उगानी चाहिए?")]
    )

    with patch.object(AsyncModels, "generate_content_stream", side_effect=mock_generate_content_stream):
        events = list(
            runner.run(
                new_message=message,
                user_id="test_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )

    has_request_input = False
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.function_call and part.function_call.name == "adk_request_input":
                    assert part.function_call.id == "more_info"
                    message_text = part.function_call.args.get("message", "")
                    assert "🌾 सर्वोत्तम फसल की सिफारिश" in message_text
                    has_request_input = True

    assert has_request_input


def test_profile_location_persistence() -> None:
    """
    Test profile location persistence reproduction flow:
    1. User: "I grow potatoes in Punjab."
    2. User: "मैं उत्तर प्रदेश में नया किसान हूँ।"
    3. User: "मुझे कौन सी फसल उगानी चाहिए?"
    Verify that:
    - Turn 2 correctly updates location to Uttar Pradesh.
    - Turn 3's recommendation is for Uttar Pradesh (not Punjab).
    """
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    with patch.object(AsyncModels, "generate_content_stream", side_effect=mock_generate_content_stream):
        # 1. User: "I grow potatoes in Punjab."
        message1 = types.Content(role="user", parts=[types.Part.from_text(text="I grow potatoes in Punjab.")])
        list(runner.run(new_message=message1, user_id="test_user", session_id=session.id, run_config=RunConfig(streaming_mode=StreamingMode.SSE)))
        
        # Check Turn 1 location is Punjab
        updated_session = session_service.get_session_sync(session_id=session.id, app_name="test", user_id="test_user")
        assert updated_session.state["farmer_profile"]["location"] == "Punjab"

        # 2. User: "मैं उत्तर प्रदेश में नया किसान हूँ।"
        message2 = types.Content(role="user", parts=[types.Part.from_text(text="मैं उत्तर प्रदेश में नया किसान हूँ।")])
        list(runner.run(new_message=message2, user_id="test_user", session_id=session.id, run_config=RunConfig(streaming_mode=StreamingMode.SSE)))
        
        # Check Turn 2 location updated to Uttar Pradesh
        updated_session2 = session_service.get_session_sync(session_id=session.id, app_name="test", user_id="test_user")
        assert updated_session2.state["farmer_profile"]["location"] == "Uttar Pradesh"

        # 3. User: "मुझे कौन सी फसल उगानी चाहिए?"
        message3 = types.Content(role="user", parts=[types.Part.from_text(text="मुझे कौन सी फसल उगानी चाहिए?")])
        events3 = list(runner.run(new_message=message3, user_id="test_user", session_id=session.id, run_config=RunConfig(streaming_mode=StreamingMode.SSE)))
        
        # Turn 4: provide the season to resume
        part = types.Part(
            function_response=types.FunctionResponse(
                name="adk_request_input",
                id="more_info",
                response={"result": "Kharif"}
            )
        )
        message4 = types.Content(role="user", parts=[part])
        events4 = list(runner.run(new_message=message4, user_id="test_user", session_id=session.id, run_config=RunConfig(streaming_mode=StreamingMode.SSE)))
        
    final_response = ""
    for event in events4:
        if event.content and event.content.parts:
            final_response += "".join(p.text for p in event.content.parts if p.text)
            
    # Verify that the subsequent crop recommendation uses Uttar Pradesh, not Punjab!
    assert "उत्तर प्रदेश" in final_response
    assert "Punjab" not in final_response

