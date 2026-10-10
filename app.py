# app.py
import os
from typing import Iterator

import streamlit as st
from dotenv import load_dotenv
from groq import Groq

from config.prompts import SYSTEM_PROMPT

load_dotenv()

# --- Configuração -----------------------------------------------------------
DEFAULT_MODEL = "openai/gpt-oss-120b"  # alternativa leve: "llama-3.1-8b-instant"
MODEL_NAME: str = os.getenv("GROQ_MODEL", DEFAULT_MODEL)
MAX_COMPLETION_TOKENS = 1024
MAX_CONTEXT_CHARS = 12_000  # ~3.000 tokens (aprox. 4 caracteres/token)

Message = dict[str, str]


# --- Lógica de domínio ------------------------------------------------------
def initial_messages() -> list[Message]:
    return [{"role": "system", "content": SYSTEM_PROMPT}]


def trim_history(messages: list[Message], max_chars: int) -> list[Message]:
    """Mantém o system prompt e as mensagens mais recentes dentro do orçamento."""
    system, history = messages[0], messages[1:]
    budget = max_chars - len(system["content"])
    kept: list[Message] = []

    for msg in reversed(history):
        budget -= len(msg["content"])
        if budget < 0 and kept:  # garante ao menos a última mensagem
            break
        kept.append(msg)

    return [system, *reversed(kept)]


def stream_reply(client: Groq, messages: list[Message]) -> Iterator[str]:
    stream = client.chat.completions.create(
        model=MODEL_NAME,
        messages=trim_history(messages, MAX_CONTEXT_CHARS),
        max_tokens=MAX_COMPLETION_TOKENS,
        stream=True,
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


# --- UI ---------------------------------------------------------------------
st.set_page_config(
    page_title="Agente de Suporte Técnico - IA", page_icon="🛠️", layout="centered"
)
st.title("🛠️ Assistente Virtual de Suporte Técnico")
st.write("Triagem inteligente, diagnóstico e suporte técnico automatizado 24/7.")

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    st.error(
        "⚠️ **Erro crítico:** A variável de ambiente `GROQ_API_KEY` não foi encontrada."
        " Crie um ficheiro `.env` na raiz com a sua chave."
    )
    st.stop()


@st.cache_resource
def get_client(key: str) -> Groq:
    return Groq(api_key=key)


client = get_client(api_key)

if "messages" not in st.session_state:
    st.session_state.messages = initial_messages()

st.sidebar.header("Painel de Controlo")
st.sidebar.info(f"Modelo Ativo: `{MODEL_NAME}`")
if st.sidebar.button("🗑️ Limpar Conversa"):
    st.session_state.messages = initial_messages()
    st.rerun()

for message in st.session_state.messages:
    if message["role"] != "system":
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

if prompt := st.chat_input("Descreva o seu problema técnico aqui..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_response = ""
        try:
            for token in stream_reply(client, st.session_state.messages):
                full_response += token
                placeholder.markdown(full_response + "▌")
            placeholder.markdown(full_response)
            st.session_state.messages.append(
                {"role": "assistant", "content": full_response}
            )
        except Exception as e:
            placeholder.error(f"Erro ao comunicar com a API da Groq: {e}")
            # Remove o prompt do utilizador para não deixar o histórico inconsistente
            # e não reenviar lixo nos próximos turnos.
            st.session_state.messages.pop()