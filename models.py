#可用模型列表，以及获得访问模型的客户端
#实际使用时可以根据自己的实际情况调整
DeepSeek_API_KEY = "DEEPSEEK_API_KEY"
import os
from langchain_openai import ChatOpenAI
from langchain_ollama import OllamaEmbeddings

def get_model_client(streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model="deepseek-v4-pro",
        api_key=os.getenv(DeepSeek_API_KEY),
        openai_api_base="https://api.deepseek.com/v1",
        temperature=0,
        streaming=streaming,
    )

def get_ollama_embeddings():
    """本地 Ollama 的 bge-m3 嵌入模型，用于文档向量化（不依赖云 API）。"""
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    return OllamaEmbeddings(model="bge-m3", base_url=ollama_host)

