import google.generativeai as genai

API_KEY = "AQ.Ab8RN6LUrCW7vjcgcaVkTEeFDqGHJKqyI_qs0v8hKSVu4C5xBg"

genai.configure(api_key=API_KEY)

try:
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content("Say hello in one sentence.")
    print(response.text)
except Exception as e:
    import traceback
    traceback.print_exc()