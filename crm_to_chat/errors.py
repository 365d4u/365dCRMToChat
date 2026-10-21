class IntegrationError(Exception):
    """Only stable codes may reach logs; payloads/credentials must not."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ContractError(IntegrationError):
    pass
