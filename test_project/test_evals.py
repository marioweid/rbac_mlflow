import os
import openai
import mlflow
from mlflow.genai.scorers import Correctness, Guidelines
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

os.environ["MLFLOW_TRACKING_SERVER_CERT_PATH"] = os.path.join(
    os.path.dirname(__file__), "..", "certs", "cert.pem"
)
mlflow.set_tracking_uri("https://mlflow.rbac.local")
mlflow.set_experiment("MyExperiment")
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 1. Define a simple QA dataset
dataset = [
    {
        "inputs": {"question": "Can MLflow manage prompts?"},
        "expectations": {"expected_response": "Yes!"},
    },
    {
        "inputs": {"question": "Can MLflow create a taco for my lunch?"},
        "expectations": {"expected_response": "No, unfortunately, MLflow is not a taco maker."},
    },
]


# 2. Define a prediction function to generate responses
def predict_fn(question: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini", messages=[{"role": "user", "content": question}]
    )
    if not response.choices[0].message.content:
        raise ValueError("OpenAI response failed.")
    return response.choices[0].message.content


# 3.Run the evaluation
results = mlflow.genai.evaluate(
    data=dataset,
    predict_fn=predict_fn,
    scorers=[
        # Built-in LLM judge
        Correctness(),
        # Custom criteria using LLM judge
        Guidelines(name="is_english", guidelines="The answer must be in English"),
    ],
)