with open("core/arc_ledger.py", "r") as f:
    content = f.read()

# Replace _sync_balance_sync logic
new_method = """    def _sync_balance_sync(self, force: bool = False):
        if not self.api_key or not self.wallet_id:
            logger.warning("Circle credentials missing i ArcLedger.")
            return

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._sync_balance(force))
        except RuntimeError:
            asyncio.run(self._sync_balance(force))"""

start_idx = content.find("    def _sync_balance_sync")
end_idx = content.find("    async def _sync_balance")

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + new_method + "\n\n" + content[end_idx:]
    with open("core/arc_ledger.py", "w") as f:
        f.write(content)
    print("Patched core/arc_ledger.py")

with open("bench_arc2.py", "r") as f:
    content = f.read()

# Fix the coroutine error in mock
content = content.replace("await asyncio.sleep(0.05)", "await asyncio.sleep(0)")
with open("bench_arc2.py", "w") as f:
    f.write(content)
