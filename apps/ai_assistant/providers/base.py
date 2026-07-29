from abc import ABC, abstractmethod


class AIProviderAdapter(ABC):
    @abstractmethod
    def generate_reply(self, messages: list[dict], language: str) -> str:
        """messages: [{"role": "user"|"assistant", "content": str}, ...] in
        chronological order. Returns the assistant's reply text."""
