# Add Nodes/Edges

Add nodes and edges to a knowledge graph

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py` — Request model for creating a knowledge graph
- `apps/coordinator-api/alembic/versions/2024_01_05_add_receipts_table.py`
- `aitbc/parallel/dependency_graph.py` — from typing import Any from aitbc.aitbc_logging import get_logger logger = get_logger(**name**) clas...
- `apps/coordinator-api/alembic/versions/add_global_marketplace.py` — Add global marketplace tables Revision ID: add_global_marketplace Revises: add_cross_chain_reputatio...
- `apps/coordinator-api/alembic/versions/add_dynamic_pricing_tables.py` — Add dynamic pricing tables Revision ID: add_dynamic_pricing_tables Revises: initial_migration Create...
- `Marketplace` exposes `POST /v1/knowledge-graph/{graph_id}/nodes` (operation `add_node_v1_knowledge_graph__graph_id__nodes_post`) — Add Node
- `Marketplace` exposes `POST /v1/knowledge-graph/{graph_id}/edges` (operation `add_edge_v1_knowledge_graph__graph_id__edges_post`) — Add Edge
- `Coordinator API` exposes `POST /v1/knowledge/graphs/{graph_id}/nodes` (operation `contribute_knowledge_v1_knowledge_graphs__graph_id__nodes_post`) — Contribute Knowledge

## Examples

- `POST /graphs/{graph_id}/nodes` (`contribute_knowledge` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `POST /graphs` (`create_knowledge_graph` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `GET /graphs` (`list_knowledge_graphs` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `GET /graphs/{graph_id}` (`get_knowledge_graph` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `GET /graphs/{graph_id}/query` (`query_knowledge_graph` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `POST /v1/knowledge-graph/{graph_id}/nodes` (`add_node_v1_knowledge_graph__graph_id__nodes_post`) on `Marketplace`
- `POST /v1/knowledge-graph/{graph_id}/edges` (`add_edge_v1_knowledge_graph__graph_id__edges_post`) on `Marketplace`
- `POST /v1/knowledge/graphs/{graph_id}/nodes` (`contribute_knowledge_v1_knowledge_graphs__graph_id__nodes_post`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `—`
