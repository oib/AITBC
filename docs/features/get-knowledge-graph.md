# Get Knowledge Graph

Get a knowledge graph

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py` — Request model for creating a knowledge graph
- `aitbc/parallel/dependency_graph.py` — from typing import Any from aitbc.aitbc_logging import get_logger logger = get_logger(__name__) clas...
- API endpoint `GET /graphs/{graph_id}` implemented in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`
- API endpoint `POST /graphs` implemented in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`
- API endpoint `GET /graphs` implemented in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`
- `Coordinator API` exposes `GET /v1/knowledge/graphs/{graph_id}` (operation `get_knowledge_graph_v1_knowledge_graphs__graph_id__get`) — Get Knowledge Graph
- `Coordinator API` exposes `GET /v1/knowledge/graphs/{graph_id}/query` (operation `query_knowledge_graph_v1_knowledge_graphs__graph_id__query_get`) — Query Knowledge Graph
- `Marketplace` exposes `GET /v1/knowledge-graph/{graph_id}` (operation `query_graph_v1_knowledge_graph__graph_id__get`) — Query Graph
## Examples

- `GET /graphs/{graph_id}` (`get_knowledge_graph` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `POST /graphs` (`create_knowledge_graph` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `GET /graphs` (`list_knowledge_graphs` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `POST /graphs/{graph_id}/nodes` (`contribute_knowledge` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `GET /graphs/{graph_id}/query` (`query_knowledge_graph` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `GET /v1/knowledge/graphs/{graph_id}` (`get_knowledge_graph_v1_knowledge_graphs__graph_id__get`) on `Coordinator API`
- `GET /v1/knowledge/graphs/{graph_id}/query` (`query_knowledge_graph_v1_knowledge_graphs__graph_id__query_get`) on `Coordinator API`
- `GET /v1/knowledge-graph/{graph_id}` (`query_graph_v1_knowledge_graph__graph_id__get`) on `Marketplace`
## Operational Notes
- **Status / Release:** `✅` / `—`
