from typing import Optional
import autogen

class DoxaChatbot(autogen.ConversableAgent):
    """
    Chatbot esterno che risponde a domande in linguaggio naturale sulla simulazione.
    Ha accesso allo YAML iniziale e a tool per estrarre dati (come export_data).
    """
    def __init__(self, engine, model: Optional[str] = None, provider: Optional[str] = None):
        self.engine = engine
        self.model = model or "llama3.1:8b"
        self.provider = provider or "ollama"
        if self.provider == "ollama":
            llm_config = {
                "config_list": [{
                    "model": self.model,
                    "base_url": "http://localhost:11434/v1",
                    "api_type": "openai",
                    "api_key": "ollama",
                    "price": [0,0]
                }],
                "temperature": 0.2,
            }
        else:
            raise ValueError(f"Provider {self.provider} not supported yet for chatbot.")
        super().__init__(
            name="DoxaChatbot",
            llm_config=llm_config,
            human_input_mode="NEVER",
            system_message=(
                "You are an assistant that answers questions about a running multi-agent simulation. "
                "You have access to tools to extract live data and the initial YAML config. "
                "If the question is hypothetical, reason about it using the current state and the rules. "
                "If it is factual, base your answer strictly on the data returned by the tools. "
                "If you cannot answer with certainty, explain what data is missing. "
                "Always call a tool before answering if data is needed. "
                "Always respond in clear, detailed English."
            ),
        )
        self._register_tools()

    def _register_tools(self):
        # Tool: export_data
        def export_data_tool(query: dict = None, format: str = "json") -> str:
            """Estrae dati dalla simulazione secondo la query (come l'API export_data)."""
            return self.engine.export_data(query, format)
        # Tool: get_yaml
        def get_yaml_tool() -> str:
            """Restituisce lo YAML iniziale della simulazione."""
            import yaml
            return yaml.dump(self.engine.raw_config)
        # Tool: get_state
        def get_state_tool() -> str:
            """Returns the current simulation state: portfolios, trades, agents, markets, and relations."""
            return self.engine.export_data({"agents": True, "portfolios": True, "trades": True, "resources": True, "markets": True, "relations": True}, format="json")
        self.register_for_llm(name="export_data", description=export_data_tool.__doc__)(export_data_tool)
        self.register_for_execution(name="export_data")(export_data_tool)
        self.register_for_llm(name="get_yaml", description=get_yaml_tool.__doc__)(get_yaml_tool)
        self.register_for_execution(name="get_yaml")(get_yaml_tool)
        self.register_for_llm(name="get_state", description=get_state_tool.__doc__)(get_state_tool)
        self.register_for_execution(name="get_state")(get_state_tool)

    def answer(self, query: str) -> str:
        """
        Answers a natural language question about the simulation using the available tools. Always in English.
        """
        # initiate_chat drives the full tool-calling loop:
        # LLM generates a tool_call → proxy executes it → LLM sees the result → final text reply.
        # generate_reply alone would return after the first turn (the tool_call) and never execute.
        proxy = autogen.UserProxyAgent(
            name="chatbot_proxy",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=8,
            code_execution_config=False,
        )
        # Share all registered tool functions with the proxy so it can execute them.
        proxy._function_map = dict(self._function_map)
        try:
            result = proxy.initiate_chat(
                self,
                message=query,
                max_turns=8,
                silent=True,
                summary_method="last_msg",
            )
            return result.summary or "No response generated."
        except Exception as exc:
            return f"Error during chatbot reasoning: {exc}"
