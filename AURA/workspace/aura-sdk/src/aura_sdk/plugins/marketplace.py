"""Plugin marketplace interface (P2 interface-only, P3+ implementation).

P2 rationale:
- Current deployment has a single subsystem plugin (`audio-qualcomm`)
- Distribution, trust verification, and versioned plugin exchange are deferred
- In-repo plugin loading remains the active runtime model
"""

from dataclasses import dataclass


@dataclass(slots=True)
class PluginPackage:
    """A distributable plugin package definition (P3+ runtime concept)."""

    name: str
    version: str
    subsystem_id: str
    author: str
    description: str
    tarball_url: str
    checksum: str
    signature: str | None
    dependencies: list[str]
    min_aura_version: str
    tested_kernels: list[str]


class PluginMarketplace:
    """P3+ plugin discovery/distribution interface.

    P2 status: callable interface exists, runtime implementation intentionally absent.
    """

    async def search(self, query: str) -> list[PluginPackage]:
        raise NotImplementedError("Plugin marketplace is available in P3+")

    async def install(self, package: PluginPackage) -> bool:
        raise NotImplementedError("Plugin marketplace is available in P3+")

    async def verify(self, package: PluginPackage) -> bool:
        raise NotImplementedError("Plugin marketplace is available in P3+")
