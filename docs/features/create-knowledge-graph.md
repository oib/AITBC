# Create Knowledge Graph

Create a knowledge graph

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py` — Request model for creating a knowledge graph
- `aitbc/parallel/dependency_graph.py` — from typing import Any from aitbc.aitbc_logging import get_logger logger = get_logger(__name__) clas...
- `apps/blockchain-node/scripts/create_genesis_wallet.py` — Create genesis wallet with secure random secp256k1 private key
- `apps/blockchain-node/create_genesis.py` — Simple script to create genesis block
- `apps/blockchain-node/create_enhanced_genesis.py` — Enhanced script to create genesis block with new features
- `Coordinator API` exposes `POST /v1/knowledge/graphs` (operation `create_knowledge_graph_v1_knowledge_graphs_post`) — Create Knowledge Graph
- `Marketplace` exposes `POST /v1/knowledge-graph` (operation `create_graph_v1_knowledge_graph_post`) — Create Graph
- `Coordinator API` exposes `GET /v1/knowledge/graphs/{graph_id}` (operation `get_knowledge_graph_v1_knowledge_graphs__graph_id__get`) — Get Knowledge Graph
## Examples

- `POST /graphs` (`create_knowledge_graph` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `GET /graphs` (`list_knowledge_graphs` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `GET /graphs/{graph_id}` (`get_knowledge_graph` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `POST /graphs/{graph_id}/nodes` (`contribute_knowledge` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `GET /graphs/{graph_id}/query` (`query_knowledge_graph` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `POST /v1/knowledge/graphs` (`create_knowledge_graph_v1_knowledge_graphs_post`) on `Coordinator API`
- `POST /v1/knowledge-graph` (`create_graph_v1_knowledge_graph_post`) on `Marketplace`
- `GET /v1/knowledge/graphs/{graph_id}` (`get_knowledge_graph_v1_knowledge_graphs__graph_id__get`) on `Coordinator API`
## Operational Notes
- **Status / Release:** `✅` / `—`
