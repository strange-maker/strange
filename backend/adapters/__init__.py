from adapters.registry import ADAPTER_CONFIGS, build_adapter
from adapters.cscec import CSCECNewsAdapter, CSCECOrganizationAdapter

__all__ = ["ADAPTER_CONFIGS", "build_adapter", "CSCECNewsAdapter", "CSCECOrganizationAdapter"]
