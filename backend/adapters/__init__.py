from adapters.registry import ADAPTER_CONFIGS, build_adapter, get_adapter_definition
from adapters.cscec import CSCECNewsAdapter, CSCECOrganizationAdapter, CSCECPDFAnnouncementAdapter

__all__ = [
    "ADAPTER_CONFIGS",
    "build_adapter",
    "get_adapter_definition",
    "CSCECNewsAdapter",
    "CSCECOrganizationAdapter",
    "CSCECPDFAnnouncementAdapter",
]
