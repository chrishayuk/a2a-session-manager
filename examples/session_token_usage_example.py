#!/usr/bin/env python3
#!/usr/bin/env python3
"""
Example demonstrating token tracking with the A2A Session Manager.

This example shows how to:
1. Track token usage across LLM interactions
2. Calculate estimated costs
3. Generate token usage reports
4. Use tiktoken for accurate token counting (if available)
"""
import json
import logging
from datetime import datetime, timezone

from a2a_session_manager.models.session import Session
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.token_usage import TokenUsage, TokenSummary, TIKTOKEN_AVAILABLE
from a2a_session_manager.storage import SessionStoreProvider, InMemorySessionStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_storage():
    """Initialize and configure the session store."""
    # Create an in-memory store for this example
    store = InMemorySessionStore()
    SessionStoreProvider.set_store(store)
    return store


def create_session_with_token_tracking():
    """Create a session with token tracking for LLM interactions."""
    logger.info("Creating a session with token tracking...")
    
    # Create a new session
    session = Session()
    logger.info(f"Created session with ID: {session.id}")
    
    # Example prompt from user
    user_prompt = "Hello, can you explain quantum computing in simple terms?"
    
    # Add user event (no token tracking needed for user)
    user_event = SessionEvent(
        message=user_prompt,
        source=EventSource.USER,
        type=EventType.MESSAGE
    )
    session.add_event(user_event)
    
    # Example LLM response
    llm_response = """
    Quantum computing is like regular computing but uses quantum bits or "qubits" instead of regular bits.
    
    Regular bits can be either 0 or 1, like a light switch that's either off or on.
    
    Qubits can be 0, 1, or both at the same time (called superposition), like a light switch that can be off, on, or somehow both off and on simultaneously.
    
    This superposition, along with another quantum property called "entanglement," allows quantum computers to explore many possibilities simultaneously, potentially solving certain problems much faster than regular computers.
    
    Think of it like checking a maze: a regular computer would try one path at a time, but a quantum computer could explore multiple paths simultaneously.
    """
    
    # Create LLM event with token tracking
    llm_event = SessionEvent.create_with_tokens(
        message=llm_response,
        prompt=user_prompt,
        completion=llm_response,
        model="gpt-4-turbo",
        source=EventSource.LLM,
        type=EventType.MESSAGE
    )
    session.add_event(llm_event)
    
    # Add another user question
    second_user_prompt = "What are some practical applications of quantum computing?"
    second_user_event = SessionEvent(
        message=second_user_prompt,
        source=EventSource.USER,
        type=EventType.MESSAGE
    )
    session.add_event(second_user_event)
    
    # Add another LLM response
    second_llm_response = """
    Here are some practical applications of quantum computing:

    1. Cryptography: Quantum computers could break current encryption methods but also enable new, more secure quantum encryption.

    2. Drug discovery: They can simulate molecular interactions more accurately, potentially accelerating new drug development.

    3. Materials science: Quantum computers can model complex materials and help develop new materials with specific properties.

    4. Optimization problems: They can find optimal solutions for complex problems like supply chain logistics, financial modeling, or traffic flow.

    5. Weather forecasting and climate modeling: Quantum computing could process the vast data needed for more accurate predictions.

    6. Artificial intelligence: Quantum algorithms may enhance machine learning tasks.

    7. Energy: Better models for fusion reactions or battery chemistry.

    Most of these applications are still in early research phases, as we don't yet have quantum computers powerful enough for commercial advantage in these areas, but progress is being made rapidly.
    """
    
    # Create second LLM event with token tracking
    second_llm_event = SessionEvent.create_with_tokens(
        message=second_llm_response,
        prompt=second_user_prompt,
        completion=second_llm_response,
        model="gpt-3.5-turbo",
        source=EventSource.LLM,
        type=EventType.MESSAGE
    )
    session.add_event(second_llm_event)
    
    # Save the session
    store = SessionStoreProvider.get_store()
    store.save(session)
    
    return session


def create_multi_model_session():
    """Create a session that uses multiple different models."""
    logger.info("Creating a session with multiple models...")
    
    # Create a new session
    session = Session()
    logger.info(f"Created multi-model session with ID: {session.id}")
    
    # Add events using different models
    models = [
        "gpt-4", 
        "gpt-3.5-turbo", 
        "claude-3-opus", 
        "claude-3-sonnet", 
        "claude-3-haiku"
    ]
    
    for i, model in enumerate(models):
        # User message
        user_message = f"Question {i+1}: Tell me about {model}."
        user_event = SessionEvent(
            message=user_message,
            source=EventSource.USER,
            type=EventType.MESSAGE
        )
        session.add_event(user_event)
        
        # LLM response - let's vary the length based on the model
        # to demonstrate different token usage patterns
        response_length = 100 * (6 - i)  # 500, 400, 300, 200, 100 chars roughly
        llm_response = f"This is a simulated response about {model}. " + "More details would be provided here. " * (6 - i)
        
        # Add LLM event with token usage tracking
        llm_event = SessionEvent.create_with_tokens(
            message=llm_response,
            prompt=user_message,
            completion=llm_response,
            model=model,
            source=EventSource.LLM,
            type=EventType.MESSAGE
        )
        session.add_event(llm_event)
    
    # Save the session
    store = SessionStoreProvider.get_store()
    store.save(session)
    
    return session


def print_token_usage_report(session: Session):
    """Print a detailed token usage report for a session."""
    logger.info(f"\n=== Token Usage Report for Session {session.id} ===")
    logger.info(f"Total tokens used: {session.total_tokens}")
    logger.info(f"Total estimated cost: ${session.total_cost:.6f}")
    
    # Print token usage by model
    logger.info("\nUsage by Model:")
    for model, usage in session.token_summary.usage_by_model.items():
        logger.info(f"  {model}:")
        logger.info(f"    Prompt tokens: {usage.prompt_tokens}")
        logger.info(f"    Completion tokens: {usage.completion_tokens}")
        logger.info(f"    Total tokens: {usage.total_tokens}")
        logger.info(f"    Estimated cost: ${usage.estimated_cost_usd:.6f}")
    
    # Print token usage by source
    logger.info("\nUsage by Source:")
    source_usage = session.get_token_usage_by_source()
    for source, summary in source_usage.items():
        logger.info(f"  {source}:")
        logger.info(f"    Total tokens: {summary.total_tokens}")
        logger.info(f"    Estimated cost: ${summary.total_estimated_cost_usd:.6f}")
    
    # Print token usage per event
    logger.info("\nEvent Token Usage:")
    for i, event in enumerate(session.events):
        if event.token_usage:
            source = event.source.value
            logger.info(f"  Event {i+1} ({source}):")
            logger.info(f"    Model: {event.token_usage.model}")
            logger.info(f"    Prompt tokens: {event.token_usage.prompt_tokens}")
            logger.info(f"    Completion tokens: {event.token_usage.completion_tokens}")
            logger.info(f"    Total tokens: {event.token_usage.total_tokens}")
            logger.info(f"    Estimated cost: ${event.token_usage.estimated_cost_usd:.6f}")


def demonstrate_token_counting():
    """Demonstrate token counting with and without tiktoken."""
    logger.info("\n=== Token Counting Demonstration ===")
    
    # Sample texts of various lengths
    texts = [
        "Hello, world!",
        "This is a slightly longer sentence to count tokens for.",
        "In natural language processing, tokenization is the process of breaking text into individual tokens. " +
        "These tokens can be words, characters, or subwords, depending on the tokenization method used. " +
        "For large language models like GPT, a custom tokenization method is used that breaks text into tokens " +
        "that may contain whole words, parts of words, or even punctuation marks."
    ]
    
    # Different models to test with
    models = ["gpt-3.5-turbo", "gpt-4", "claude-3-sonnet"]
    
    for text in texts:
        logger.info(f"\nText: {text[:50]}..." if len(text) > 50 else f"\nText: {text}")
        logger.info(f"Length: {len(text)} characters")
        
        for model in models:
            token_count = TokenUsage.count_tokens(text, model)
            logger.info(f"  {model}: {token_count} tokens")
    
    # Note about tiktoken availability
    if TIKTOKEN_AVAILABLE:
        logger.info("\nUsing tiktoken for accurate token counting")
    else:
        logger.info("\nTiktoken not available. Using approximation (4 chars ≈ 1 token)")
        logger.info("Install tiktoken for more accurate counts: pip install tiktoken")


def tracking_conversation_costs():
    """Demonstrate tracking costs throughout a conversation."""
    logger.info("\n=== Tracking Conversation Costs ===")
    
    # Create a new session
    session = Session()
    logger.info(f"Created cost tracking session with ID: {session.id}")
    
    # Define a conversation
    conversation = [
        {"role": "user", "content": "I need help planning a trip to Japan in spring. What are the best places to see cherry blossoms?"},
        {"role": "assistant", "content": "Japan is famous for its cherry blossoms (sakura) in spring! Here are some of the best places to see them:\n\n1. **Tokyo** - Ueno Park, Shinjuku Gyoen, and Chidorigafuchi are popular spots.\n\n2. **Kyoto** - The Philosopher's Path, Maruyama Park, and Arashiyama are magnificent.\n\n3. **Osaka** - Osaka Castle Park offers beautiful views.\n\n4. **Hiroshima** - Particularly at Miyajima Island.\n\n5. **Fukuoka** - Maizuru Park is known for its 1,000 cherry trees.\n\n6. **Mount Yoshino** in Nara - One of Japan's most famous cherry blossom spots with over 30,000 trees.\n\nThe cherry blossom season typically runs from late March to early April, but timing varies by location (earlier in southern Japan, later in the north). Would you like more specific information about any of these locations or advice on planning your itinerary?"},
        {"role": "user", "content": "I'd like to know more about Kyoto. How many days should I spend there, and what other attractions should I see besides cherry blossoms?"},
        {"role": "assistant", "content": "Kyoto deserves at least 3-4 days in your itinerary, though many visitors wish they had allocated more time for this beautiful historic city. Here's what I recommend:\n\n**Time in Kyoto:** 3-4 days minimum, 5-6 days ideal if you want to explore thoroughly\n\n**Besides cherry blossoms, don't miss these attractions:**\n\n1. **Fushimi Inari Shrine** - Famous for its thousands of vermilion torii gates\n\n2. **Kinkaku-ji (Golden Pavilion)** - A stunning Zen temple covered in gold leaf\n\n3. **Arashiyama Bamboo Grove** - A magical forest of towering bamboo\n\n4. **Gion District** - The famous geisha district with traditional wooden machiya houses\n\n5. **Kiyomizu-dera Temple** - Offers spectacular views of the city\n\n6. **Nijo Castle** - Known for its \"nightingale floors\" that chirp when walked upon\n\n7. **Philosopher's Path** - Beautiful for cherry blossoms but lovely year-round\n\n8. **Nishiki Market** - \"Kyoto's Kitchen\" with amazing food stalls\n\n9. **Ryoan-ji Temple** - Famous rock garden and peaceful grounds\n\n10. **Kimono/Yukata Experience** - Many shops offer rental services where you can dress in traditional attire\n\n**Day trips from Kyoto:**\n- Nara (to see the famous deer park and Todai-ji Temple)\n- Osaka (for modern contrast, food, and nightlife)\n- Uji (for matcha and the beautiful Byodo-in Temple)\n\nWould you like more specific information about any of these attractions or recommendations for accommodations in Kyoto?"},
        {"role": "user", "content": "That's great information! What about transportation? What's the best way to get around Japan and specifically in Kyoto?"},
    ]
    
    # Models to use (alternating between GPT-4 and GPT-3.5 for demonstration)
    models = ["gpt-4", "gpt-3.5-turbo"]
    model_index = 0
    
    # Simulate the conversation and track costs
    for i, msg in enumerate(conversation):
        role = msg["role"]
        content = msg["content"]
        
        if role == "user":
            # Add user message (no token tracking)
            user_event = SessionEvent(
                message=content,
                source=EventSource.USER,
                type=EventType.MESSAGE
            )
            session.add_event(user_event)
            logger.info(f"Added user message ({len(content)} chars)")
            
        elif role == "assistant":
            # Use alternating models
            model = models[model_index % len(models)]
            model_index += 1
            
            # Get the previous user message as the prompt
            prompt = conversation[i-1]["content"] if i > 0 else ""
            
            # Create assistant event with token tracking
            assistant_event = SessionEvent.create_with_tokens(
                message=content,
                prompt=prompt,
                completion=content,
                model=model,
                source=EventSource.LLM,
                type=EventType.MESSAGE
            )
            session.add_event(assistant_event)
            
            # Log token usage for this message
            tokens = assistant_event.token_usage.total_tokens
            cost = assistant_event.token_usage.estimated_cost_usd
            logger.info(f"Added assistant message using {model}: {tokens} tokens, ${cost:.6f}")
            
            # Log running total
            logger.info(f"Running total: {session.total_tokens} tokens, ${session.total_cost:.6f}")
    
    # Add the final assistant response
    final_response = """
    Japan has an excellent public transportation system! Here's a guide for getting around:

    **For travel between cities:**
    
    1. **Japan Rail (JR) Pass**: If you're visiting multiple cities, this is highly recommended. It's a cost-effective pass available only to foreign tourists that gives unlimited access to JR trains (including most Shinkansen/bullet trains) for 7, 14, or 21 days. You must purchase it before arriving in Japan.
    
    2. **Shinkansen (Bullet Train)**: The fastest way to travel between major cities. Tokyo to Kyoto takes only about 2.5 hours.
    
    3. **Domestic Flights**: Useful for longer distances (like Tokyo to Hokkaido or Okinawa).
    
    **In Kyoto specifically:**
    
    1. **City Bus**: Kyoto's bus network is extensive and the primary way tourists get around. The flat-fare system makes it easy to use. Consider purchasing a one-day bus pass for unlimited rides.
    
    2. **Subway**: Kyoto has two subway lines that are useful for certain destinations, though less comprehensive than the bus system.
    
    3. **Bicycle Rental**: Kyoto is relatively flat and compact, making cycling a pleasant option in good weather.
    
    4. **Walking**: Many of Kyoto's attractions within specific districts (like Higashiyama or Arashiyama) are best explored on foot.
    
    5. **Taxis**: Readily available and a good option for destinations not easily reached by bus or when you're tired after a long day of sightseeing.
    
    **Transportation tips:**
    
    - Get an IC Card (Suica, PASMO, ICOCA) for convenient payment on trains, buses, subways, and even in convenience stores.
    - Google Maps works well in Japan for navigation and train/bus schedules.
    - Downtown Kyoto attractions are usually 15-30 minutes apart by bus.
    - The Arashiyama and Higashiyama districts are best explored by dedicating a full day to each.
    - During cherry blossom season, public transportation will be more crowded, so allow extra travel time.
    
    Would you like specific advice about getting to certain attractions in Kyoto or more information about the JR Pass?
    """
    
    # Use GPT-4 for final response
    final_event = SessionEvent.create_with_tokens(
        message=final_response,
        prompt=conversation[-1]["content"],
        completion=final_response,
        model="gpt-4",
        source=EventSource.LLM,
        type=EventType.MESSAGE
    )
    session.add_event(final_event)
    
    # Log final token usage
    tokens = final_event.token_usage.total_tokens
    cost = final_event.token_usage.estimated_cost_usd
    logger.info(f"Added final assistant message: {tokens} tokens, ${cost:.6f}")
    logger.info(f"Final total: {session.total_tokens} tokens, ${session.total_cost:.6f}")
    
    # Save the session
    store = SessionStoreProvider.get_store()
    store.save(session)
    
    return session


def main():
    """Main function demonstrating the token tracking functionality."""
    logger.info("Starting A2A Session Manager Token Tracking example")
    
    # Setup storage
    store = setup_storage()
    
    # Check if tiktoken is available
    logger.info(f"Tiktoken available: {TIKTOKEN_AVAILABLE}")
    
    # Create basic session with token tracking
    session = create_session_with_token_tracking()
    print_token_usage_report(session)
    
    # Create session with multiple models
    multi_model_session = create_multi_model_session()
    print_token_usage_report(multi_model_session)
    
    # Demonstrate token counting
    demonstrate_token_counting()
    
    # Demonstrate tracking conversation costs
    cost_tracking_session = tracking_conversation_costs()
    print_token_usage_report(cost_tracking_session)
    
    logger.info("A2A Session Manager Token Tracking example completed")


if __name__ == "__main__":
    main()