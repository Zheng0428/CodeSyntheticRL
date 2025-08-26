from dotenv import load_dotenv
# Load environment variables from .env file if it exists
load_dotenv()
# API configuration with environment variables or defaults
# BASE_URL = "https://search-va.byteintl.net/gpt/openapi/online/v2/crawl/openai/deployments/gpt_openapi" #http://maas.byteintl.net/gateway/v1/chat/completions
BASE_URL = 'https://search-va.byteintl.net/gpt/openapi/online/v2/crawl'
# API_KEY = "54nhP5uBXv7iWgHJ4bWMD90Nwkn09BXN"  # Replace with your actual API key
# API_KEY = 'ZHFA24cLbMWVdN1qI4jJ4WVbt6PkaJKP_GPT_AK'
API_KEY = 'x1Whe5nkEi8T2CGEqn6s9F7jtPGUxI7E_GPT_AK'
MODEL = "gpt-4o-2024-11-20" # gcp-claude37-sonnet/gemini-2.5-pro-preview-05-06/gpt-4o-2024-11-20
MAX_TOKENS = 16000
SYSTEM_PROMPT = "You are a very helpful assistant."
LEETCODE_PATH = '/mnt/bn/tiktok-mm-5/aiic/users/tianyu/dataset/CodeSyntheticData/merged_leetcode.jsonl'