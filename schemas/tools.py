from pydantic import BaseModel, Field


class CCTPTransferToolSchema(BaseModel):
    """
    Schema for the LLM Copilot to invoke a CCTP Cross-Chain Transfer.
    """

    amount: float = Field(..., gt=0.0, description="Amount of USDC to bridge")
    source_chain: str = Field(
        ...,
        description="Source chain name (e.g., 'ethereum_sepolia', 'arbitrum_sepolia')",
    )
    target_chain: str = Field(
        ...,
        description="Destination chain name (e.g., 'arbitrum_sepolia', 'ethereum_sepolia')",
    )
    destination_address: str = Field(
        ..., description="The wallet address to receive the USDC on the target chain"
    )


# To use with OpenAI function calling, you would dump this to JSON schema:
# CCTPTransferToolSchema.model_json_schema()
