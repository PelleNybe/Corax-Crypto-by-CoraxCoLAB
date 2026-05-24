# Circle CCTP Cross-Chain Integration

## Overview

Corax Crypto utilizes Circle's **Cross-Chain Transfer Protocol (CCTP)** to seamlessly and securely move USDC liquidity between different blockchain networks in response to cross-chain arbitrage opportunities detected by the high-frequency trading engine.

The CCTP process employs a native "Burn and Mint" mechanism, ensuring that liquidity is transferred without the need for wrapped assets or traditional lock-and-mint bridges, resulting in lower slippage and faster execution for high-frequency strategies.

## Architecture

The integration is encapsulated primarily within the `CCTPManager` class (`execution/bridge_manager.py`).

The lifecycle of a cross-chain transfer is executed in three distinct, asynchronous phases:

1.  **Initiation (Burn)**: `initiate_transfer(amount, source_chain, target_chain, destination_address)`
    *   Initiates a transaction on the source chain to burn the specified amount of USDC.
    *   This is executed using the Circle Developer API (W3S).
    *   Returns a transaction hash or message hash.
2.  **Attestation (Polling)**: `poll_attestation(message_hash)`
    *   The engine asynchronously polls the Circle IRIS API (`https://iris-api.circle.com/v1/attestations/{messageHash}`) to wait for an attestation signature.
    *   Implemented with robust exponential backoff to avoid rate limits and handle network delays.
3.  **Completion (Mint)**: `complete_transfer(attestation, target_chain, message_bytes)`
    *   Once the attestation is received, a transaction is submitted to the target chain's MessageTransmitter contract to mint the equivalent amount of USDC at the destination address.

## LLM Copilot Tooling

The AI Copilot has been equipped with a new tool schema (`execute_cctp_transfer`) allowing it to parse natural language commands and execute bridge operations.

**Example Command:**
> "We've detected a significant spread on Arbitrum. Bridge 500 USDC from Ethereum Sepolia to Arbitrum Sepolia immediately."

The Copilot parses this intent, validates the parameters using the Pydantic schema in `schemas/tools.py`, and dispatches a `CCTP_TRANSFER` command to the `OrderManager` queue for asynchronous execution.

## Network Map (Domain IDs)

The `CCTPManager` handles internal mapping of friendly network names to CCTP Domain IDs.

| Network | Domain ID |
| :--- | :--- |
| Ethereum / Sepolia | 0 |
| Avalanche / Fuji | 1 |
| Optimism / Sepolia | 2 |
| Arbitrum / Sepolia | 3 |
| Solana / Devnet | 5 |
| Base / Sepolia | 6 |
| Polygon / Amoy | 7 |

## Execution Flow

1.  **Arbitrage Engine** detects an opportunity spread that requires shifting liquidity.
2.  **Copilot** analyzes the macro regime and the user's intent.
3.  **Telegram Interface** passes the parsed parameters to the `OrderManager`.
4.  **OrderManager** queues the `CCTP_TRANSFER` action.
5.  **CCTPManager** handles the full Burn -> Poll -> Mint lifecycle without blocking the main event loop.

## Security & Risk Management

All CCTP transfers are bound by the same global state variables and `RiskManager` constraints as standard spot trades. If the Kill Switch is activated (`KILL_SWITCH`), bridge operations will be halted to protect capital.
