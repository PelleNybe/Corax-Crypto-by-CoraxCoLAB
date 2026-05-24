# flake8: noqa

if __import__("typing").TYPE_CHECKING:
    # import apis into api package
    from circle.web3.configurations.api.developer_account_api import DeveloperAccountApi
    from circle.web3.configurations.api.faucet_api import FaucetApi
    from circle.web3.configurations.api.health_api import HealthApi
    from circle.web3.configurations.api.monitor_tokens_api import MonitorTokensApi
    from circle.web3.configurations.api.webhook_subscriptions_api import WebhookSubscriptionsApi
    
else:
    from lazy_imports import LazyModule, as_package, load

    load(
        LazyModule(
            *as_package(__file__),
            """# import apis into api package
from circle.web3.configurations.api.developer_account_api import DeveloperAccountApi
from circle.web3.configurations.api.faucet_api import FaucetApi
from circle.web3.configurations.api.health_api import HealthApi
from circle.web3.configurations.api.monitor_tokens_api import MonitorTokensApi
from circle.web3.configurations.api.webhook_subscriptions_api import WebhookSubscriptionsApi

""",
            name=__name__,
            doc=__doc__,
        )
    )
