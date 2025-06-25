#!/usr/bin/env python3
"""
Script to improve bot responses when no relevant Slack data exists
"""

# This shows how to modify the generation service to prevent hallucination
# when no relevant context is found

def improve_generation_prompt():
    """
    Example of how to modify the generation prompt to prevent hallucination
    """
    
    improved_prompt = """
    You are a sales assistant. Answer questions based ONLY on the provided context.

    CRITICAL RULES:
    1. If NO relevant Slack messages are found about a specific company, say: 
       "I couldn't find any Slack messages about [company] in our indexed channels."
    
    2. If NO relevant Salesforce data exists, say:
       "I couldn't find any Salesforce records for [company]."
    
    3. NEVER fabricate or invent information not in the context.
    
    4. If the context contains general messages but nothing specific to the query, say:
       "While I found some general discussions, none specifically mention [topic]."

    5. Always be honest about limitations in available data.

    Context: {context}
    
    Question: {question}
    
    Response:"""
    
    return improved_prompt

def example_improved_responses():
    """Example of better responses for empty results"""
    
    examples = {
        "zillow_no_slack": {
            "query": "What is the exact last slack message about Zillow?",
            "bad_response": "Based on strategic planning discussions and NDA execution...",
            "good_response": "I couldn't find any Slack messages about Zillow in our indexed channels. However, I do have Salesforce records for Zillow Group and a contact at mmathew@zillowgroup.com. Would you like me to show you the Salesforce information instead?"
        },
        
        "adobe_no_data": {
            "query": "Tell me about Adobe discussions",
            "bad_response": "Adobe has been a key strategic partner with ongoing negotiations...",
            "good_response": "I couldn't find any specific Slack messages or Salesforce records about Adobe in our current data. You might want to check if Adobe discussions happened in channels we haven't indexed yet, or create new records if this is a new prospect."
        }
    }
    
    return examples

# Instructions for implementation:
print("""
🔧 To Fix Hallucination Issues:

1. Update generation prompts to be more strict about context
2. Add explicit checks for empty/irrelevant results  
3. Provide helpful alternatives when primary data is missing
4. Be transparent about data limitations

Example fix for app/rag/generation.py:
- Add validation for relevant context before generating response
- Include explicit "no data found" handling
- Suggest alternative searches or actions
""")

if __name__ == "__main__":
    print("🚀 Hallucination Prevention Improvements")
    print("\nSee the functions above for implementation guidance")
    
    examples = example_improved_responses()
    for key, example in examples.items():
        print(f"\n--- {key.upper()} ---")
        print(f"Query: {example['query']}")
        print(f"❌ Bad: {example['bad_response']}")
        print(f"✅ Good: {example['good_response']}") 