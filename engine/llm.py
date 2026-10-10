"""Optional cloud LLM fallback (Azure OpenAI). Used ONLY when keyword routing can't match a question.
The model just picks a field NAME from the current hospital's list; our code then returns that field's
exact guide text. The model never writes the answer, so it cannot invent a rule.

Set: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT (optional AZURE_OPENAI_API_VERSION).
"""
import os


def pick_field(question, fields):
    ep, key, dep = (os.getenv("AZURE_OPENAI_ENDPOINT"), os.getenv("AZURE_OPENAI_API_KEY"),
                    os.getenv("AZURE_OPENAI_DEPLOYMENT"))
    if not (ep and key and dep):
        return None
    try:
        from openai import AzureOpenAI
        client = AzureOpenAI(azure_endpoint=ep, api_key=key,
                             api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01"))
        r = client.chat.completions.create(
            model=dep, temperature=0, max_tokens=40,
            messages=[{"role": "system", "content": "Pick the ONE guide field that answers the provider's question. "
                       "Reply with the exact field name from the list, or NONE."},
                      {"role": "user", "content": f"Fields: {fields}\nQuestion: {question}"}])
        name = r.choices[0].message.content.strip().strip('"').strip()
        return name if name in fields else None
    except Exception:
        return None
