import asyncio
import sys
from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig

async def test_sdk():
    print("Initializing Antigravity Agent...")
    config = LocalAgentConfig(
        system_instructions="You are an expert AI assistant testing the AgentRelay local harness. Keep responses concise.",
        capabilities=CapabilitiesConfig(),
    )
    
    try:
        async with Agent(config) as agent:
            print("Agent initialized successfully. Sending prompt...")
            prompt = "Say hello from AgentRelay, list 2 key features of a remote agent bridge, and finish."
            response = await agent.chat(prompt)
            
            print("\n--- STREAMING RESPONSE TEXT ---")
            async for token in response:
                sys.stdout.write(token)
                sys.stdout.flush()
            print("\n-------------------------------\n")
            
            # Checking usage metadata
            usage = response.usage_metadata
            if usage:
                print("Usage Metadata Captured:")
                print(f"  Prompt tokens: {usage.prompt_token_count}")
                print(f"  Candidates tokens: {usage.candidates_token_count}")
                print(f"  Cached content tokens: {usage.cached_content_token_count}")
                print(f"  Thoughts tokens: {usage.thoughts_token_count}")
                print(f"  Total tokens: {usage.total_token_count}")
            else:
                print("No usage metadata returned.")
                
            print("\nTest completed successfully!")
            
    except Exception as e:
        print(f"Error during SDK test: {e}", file=sys.stderr)
        raise

if __name__ == "__main__":
    asyncio.run(test_sdk())
