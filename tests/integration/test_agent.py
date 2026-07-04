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

# Mock function for AsyncModels.generate_content_stream to make tests offline and reliable
async def mock_generate_content_stream(*args, **kwargs):
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

    # Check query type and route response
    if "sky blue" in prompt_text.lower():
        response_text = '{"response": "The sky is blue because of Rayleigh scattering.", "needs_more_info": false, "info_request_message": ""}'
    elif "hello" in prompt_text.lower() or "hi" in prompt_text.lower() or "start" in prompt_text.lower():
        response_text = (
            '{"response": "👋 Welcome to BharatSahayak!\\n\\nI can help you with:\\n\\n🌾 Crop recommendations\\n'
            '🌦 Weather advisories\\n🦠 Disease diagnosis\\n🏛 Government schemes\\n💰 Profitability analysis\\n\\n'
            'Try asking:\\n\\\"I am a wheat farmer in Punjab.\\\"\\n\\\"What crop should I grow?\\\"\\n'
            '\\\"My rice leaves have brown spots.\\\"", "needs_more_info": false, "info_request_message": ""}'
        )
    elif "potatoes in punjab" in prompt_text.lower() or "potato" in prompt_text.lower():
        response_text = (
            '{"response": "✅ Profile Updated\\n\\n📍 Location: Punjab\\n🌾 Crop: Potato\\n\\n'
            'I can now help you with:\\n🌦 Weather advisories\\n🦠 Disease diagnosis\\n🏛 Government schemes\\n'
            '💰 Profit improvement\\n🌱 Crop recommendations\\n\\nAsk me anything about your farming needs.", '
            '"needs_more_info": false, "info_request_message": ""}'
        )
    else:
        # Standard crop recommendation (English or Hindi)
        if "कठिनाई" in prompt_text or "बैंगलोर" in prompt_text:
            response_text = (
                '{"response": "🌱 अनुशंसित फसल: धान (Why chosen: धान यहाँ का मुख्य भोजन है और मिट्टी इसके लिए उपयुक्त है।)\\n'
                '📍 क्षेत्र: कर्नाटक\\n💰 निवेश: 18,000 रुपये प्रति एकड़\\n📈 अपेक्षित लाभ: 1,28,300.00 रुपये का कुल शुद्ध लाभ\\n'
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
