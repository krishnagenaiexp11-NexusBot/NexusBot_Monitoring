import os
import json
import urllib.request
import urllib.error
import time

AI_PROVIDER = "gemini"
AI_MODEL = os.getenv("NEXUSBOT_AI_MODEL", "gemini-1.5-flash-latest")


class GeminiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = AI_MODEL

    def generate_content(self, prompt: str, temperature: float = 0.2) -> dict:
        """
        Sends prompt to Gemini REST endpoint.
        Returns a dictionary containing raw response markdown, estimated tokens, and time taken.
        """
        try:
            return self._call_api(self.model, prompt, temperature)
        except Exception as e:
            if ("HTTP 404" in str(e) or "404" in str(e)) and self.model == "gemini-1.5-flash-latest":
                # Fallback to gemini-2.0-flash on HTTP 404
                try:
                    return self._call_api("gemini-2.0-flash", prompt, temperature)
                except Exception as inner_e:
                    raise Exception(f"Failed calling Gemini API (both gemini-1.5-flash-latest and gemini-2.0-flash failed): {str(inner_e)}")
            else:
                raise e

    def _call_api(self, model_name: str, prompt: str, temperature: float) -> dict:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "topP": 0.95,
                "maxOutputTokens": 2048
            }
        }
        json_payload = json.dumps(data).encode("utf-8")
        
        prompt_tokens = len(prompt) // 4
        
        start_time = time.time()
        req = urllib.request.Request(url, data=json_payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                duration = time.time() - start_time
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                
                text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                completion_tokens = len(text) // 4
                
                return {
                    "raw_response_md": text,
                    "tokens_estimated": prompt_tokens + completion_tokens,
                    "duration_seconds": duration,
                    "model": model_name,
                    "provider": AI_PROVIDER
                }
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise Exception(f"Gemini REST Error (HTTP {e.code}): {error_body}")
        except Exception as e:
            raise Exception(f"Failed to communicate with Gemini API: {str(e)}")
