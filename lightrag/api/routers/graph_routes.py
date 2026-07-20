"""
This module contains all graph-related routes for the LightRAG API.
"""

from typing import Optional, Dict, Any
import json
import os
import time
import traceback
from collections import Counter
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, Query, HTTPException
from pydantic import BaseModel, Field, field_validator

from lightrag.base import DeletionResult
import unicodedata

from lightrag.maintenance.dedup import NodeView, plan_dedup
from lightrag.maintenance.edition_rename import (
    EDITION_YEARS,
    _new_name,
    parsed_artifact_renames,
    plan_rename,
)
from lightrag.utils import logger
from lightrag.utils_pipeline import parsed_dir, sidecar_uri_for
from ..utils_api import get_combined_auth_dependency
from .document_routes import check_pipeline_busy_or_raise


class EntityUpdateRequest(BaseModel):
    entity_name: str
    updated_data: Dict[str, Any]
    allow_rename: bool = False
    allow_merge: bool = False


class RelationUpdateRequest(BaseModel):
    source_id: str
    target_id: str
    updated_data: Dict[str, Any]


class EntityMergeRequest(BaseModel):
    entities_to_change: list[str] = Field(
        ...,
        description="List of entity names to be merged and deleted. These are typically duplicate or misspelled entities.",
        min_length=1,
        examples=[["Elon Msk", "Ellon Musk"]],
    )
    entity_to_change_into: str = Field(
        ...,
        description="Target entity name that will receive all relationships from the source entities. This entity will be preserved.",
        min_length=1,
        examples=["Elon Musk"],
    )


class EntityCreateRequest(BaseModel):
    entity_name: str = Field(
        ...,
        description="Unique name for the new entity",
        min_length=1,
        examples=["Tesla"],
    )
    entity_data: Dict[str, Any] = Field(
        ...,
        description="Dictionary containing entity properties. Common fields include 'description' and 'entity_type'.",
        examples=[
            {
                "description": "Electric vehicle manufacturer",
                "entity_type": "ORGANIZATION",
            }
        ],
    )


class DeleteEntityRequest(BaseModel):
    entity_name: str = Field(..., description="The name of the entity to delete.")

    @field_validator("entity_name", mode="after")
    @classmethod
    def validate_entity_name(cls, entity_name: str) -> str:
        if not entity_name or not entity_name.strip():
            raise ValueError("Entity name cannot be empty")
        return entity_name.strip()


class DeleteRelationRequest(BaseModel):
    source_entity: str = Field(..., description="The name of the source entity.")
    target_entity: str = Field(..., description="The name of the target entity.")

    @field_validator("source_entity", "target_entity", mode="after")
    @classmethod
    def validate_entity_names(cls, entity_name: str) -> str:
        if not entity_name or not entity_name.strip():
            raise ValueError("Entity name cannot be empty")
        return entity_name.strip()


class RelationCreateRequest(BaseModel):
    source_entity: str = Field(
        ...,
        description="Name of the source entity. This entity must already exist in the knowledge graph.",
        min_length=1,
        examples=["Elon Musk"],
    )
    target_entity: str = Field(
        ...,
        description="Name of the target entity. This entity must already exist in the knowledge graph.",
        min_length=1,
        examples=["Tesla"],
    )
    relation_data: Dict[str, Any] = Field(
        ...,
        description="Dictionary containing relationship properties. Common fields include 'description', 'keywords', and 'weight'.",
        examples=[
            {
                "description": "Elon Musk is the CEO of Tesla",
                "keywords": "CEO, founder",
                "weight": 1.0,
            }
        ],
    )


def create_graph_routes(rag, api_key: Optional[str] = None):
    # Fresh router per call. A module-level instance would accumulate
    # duplicate routes when the factory is invoked more than once in the
    # same process (e.g. across tests), which triggers FastAPI's
    # "Duplicate Operation ID" warnings.
    router = APIRouter(tags=["graph"])

    combined_auth = get_combined_auth_dependency(api_key)

    @router.get("/graph/label/list", dependencies=[Depends(combined_auth)])
    async def get_graph_labels():
        """
        Get all graph labels

        Returns:
            List[str]: List of graph labels
        """
        try:
            return await rag.get_graph_labels()
        except Exception as e:
            logger.error(f"Error getting graph labels: {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500, detail=f"Error getting graph labels: {str(e)}"
            )

    @router.get("/graph/label/popular", dependencies=[Depends(combined_auth)])
    async def get_popular_labels(
        limit: int = Query(
            300, description="Maximum number of popular labels to return", ge=1, le=1000
        ),
    ):
        """
        Get popular labels by node degree (most connected entities)

        Args:
            limit (int): Maximum number of labels to return (default: 300, max: 1000)

        Returns:
            List[str]: List of popular labels sorted by degree (highest first)
        """
        try:
            return await rag.chunk_entity_relation_graph.get_popular_labels(limit)
        except Exception as e:
            logger.error(f"Error getting popular labels: {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500, detail=f"Error getting popular labels: {str(e)}"
            )

    @router.get("/graph/label/search", dependencies=[Depends(combined_auth)])
    async def search_labels(
        q: str = Query(..., description="Search query string"),
        limit: int = Query(
            50, description="Maximum number of search results to return", ge=1, le=100
        ),
    ):
        """
        Search labels with fuzzy matching

        Args:
            q (str): Search query string
            limit (int): Maximum number of results to return (default: 50, max: 100)

        Returns:
            List[str]: List of matching labels sorted by relevance
        """
        try:
            return await rag.chunk_entity_relation_graph.search_labels(q, limit)
        except Exception as e:
            logger.error(f"Error searching labels with query '{q}': {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500, detail=f"Error searching labels: {str(e)}"
            )

    @router.get("/graphs", dependencies=[Depends(combined_auth)])
    async def get_knowledge_graph(
        label: str = Query(..., description="Label to get knowledge graph for"),
        max_depth: int = Query(3, description="Maximum depth of graph", ge=1),
        max_nodes: int = Query(1000, description="Maximum nodes to return", ge=1),
    ):
        """
        Retrieve a connected subgraph of nodes where the label includes the specified label.
        When reducing the number of nodes, the prioritization criteria are as follows:
            1. Hops(path) to the staring node take precedence
            2. Followed by the degree of the nodes

        Args:
            label (str): Label of the starting node
            max_depth (int, optional): Maximum depth of the subgraph,Defaults to 3
            max_nodes: Maxiumu nodes to return

        Returns:
            Dict[str, List[str]]: Knowledge graph for label
        """
        try:
            # Log the label parameter to check for leading spaces
            logger.debug(
                f"get_knowledge_graph called with label: '{label}' (length: {len(label)}, repr: {repr(label)})"
            )

            return await rag.get_knowledge_graph(
                node_label=label,
                max_depth=max_depth,
                max_nodes=max_nodes,
            )
        except Exception as e:
            logger.error(f"Error getting knowledge graph for label '{label}': {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500, detail=f"Error getting knowledge graph: {str(e)}"
            )

    @router.get("/graph/entity/exists", dependencies=[Depends(combined_auth)])
    async def check_entity_exists(
        name: str = Query(..., description="Entity name to check"),
    ):
        """
        Check if an entity with the given name exists in the knowledge graph

        Args:
            name (str): Name of the entity to check

        Returns:
            Dict[str, bool]: Dictionary with 'exists' key indicating if entity exists
        """
        try:
            exists = await rag.chunk_entity_relation_graph.has_node(name)
            return {"exists": exists}
        except Exception as e:
            logger.error(f"Error checking entity existence for '{name}': {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500, detail=f"Error checking entity existence: {str(e)}"
            )

    @router.post("/graph/entity/edit", dependencies=[Depends(combined_auth)])
    async def update_entity(request: EntityUpdateRequest):
        """
        Update an entity's properties in the knowledge graph

        This endpoint allows updating entity properties, including renaming entities.
        When renaming to an existing entity name, the behavior depends on allow_merge:

        Args:
            request (EntityUpdateRequest): Request containing:
                - entity_name (str): Name of the entity to update
                - updated_data (Dict[str, Any]): Dictionary of properties to update
                - allow_rename (bool): Whether to allow entity renaming (default: False)
                - allow_merge (bool): Whether to merge into existing entity when renaming
                                     causes name conflict (default: False)

        Returns:
            Dict with the following structure:
            {
                "status": "success",
                "message": "Entity updated successfully" | "Entity merged successfully into 'target_name'",
                "data": {
                    "entity_name": str,        # Final entity name
                    "description": str,        # Entity description
                    "entity_type": str,        # Entity type
                    "source_id": str,         # Source chunk IDs
                    ...                       # Other entity properties
                },
                "operation_summary": {
                    "merged": bool,           # Whether entity was merged into another
                    "merge_status": str,      # "success" | "failed" | "not_attempted"
                    "merge_error": str | None, # Error message if merge failed
                    "operation_status": str,  # "success" | "partial_success" | "failure"
                    "target_entity": str | None, # Target entity name if renaming/merging
                    "final_entity": str,      # Final entity name after operation
                    "renamed": bool           # Whether entity was renamed
                }
            }

        operation_status values explained:
            - "success": All operations completed successfully
                * For simple updates: entity properties updated
                * For renames: entity renamed successfully
                * For merges: non-name updates applied AND merge completed

            - "partial_success": Update succeeded but merge failed
                * Non-name property updates were applied successfully
                * Merge operation failed (entity not merged)
                * Original entity still exists with updated properties
                * Use merge_error for failure details

            - "failure": Operation failed completely
                * If merge_status == "failed": Merge attempted but both update and merge failed
                * If merge_status == "not_attempted": Regular update failed
                * No changes were applied to the entity

        merge_status values explained:
            - "success": Entity successfully merged into target entity
            - "failed": Merge operation was attempted but failed
            - "not_attempted": No merge was attempted (normal update/rename)

        Behavior when renaming to an existing entity:
            - If allow_merge=False: Raises ValueError with 400 status (default behavior)
            - If allow_merge=True: Automatically merges the source entity into the existing target entity,
                                  preserving all relationships and applying non-name updates first

        Example Request (simple update):
            POST /graph/entity/edit
            {
                "entity_name": "Tesla",
                "updated_data": {"description": "Updated description"},
                "allow_rename": false,
                "allow_merge": false
            }

        Example Response (simple update success):
            {
                "status": "success",
                "message": "Entity updated successfully",
                "data": { ... },
                "operation_summary": {
                    "merged": false,
                    "merge_status": "not_attempted",
                    "merge_error": null,
                    "operation_status": "success",
                    "target_entity": null,
                    "final_entity": "Tesla",
                    "renamed": false
                }
            }

        Example Request (rename with auto-merge):
            POST /graph/entity/edit
            {
                "entity_name": "Elon Msk",
                "updated_data": {
                    "entity_name": "Elon Musk",
                    "description": "Corrected description"
                },
                "allow_rename": true,
                "allow_merge": true
            }

        Example Response (merge success):
            {
                "status": "success",
                "message": "Entity merged successfully into 'Elon Musk'",
                "data": { ... },
                "operation_summary": {
                    "merged": true,
                    "merge_status": "success",
                    "merge_error": null,
                    "operation_status": "success",
                    "target_entity": "Elon Musk",
                    "final_entity": "Elon Musk",
                    "renamed": true
                }
            }

        Example Response (partial success - update succeeded but merge failed):
            {
                "status": "success",
                "message": "Entity updated successfully",
                "data": { ... },  # Data reflects updated "Elon Msk" entity
                "operation_summary": {
                    "merged": false,
                    "merge_status": "failed",
                    "merge_error": "Target entity locked by another operation",
                    "operation_status": "partial_success",
                    "target_entity": "Elon Musk",
                    "final_entity": "Elon Msk",  # Original entity still exists
                    "renamed": true
                }
            }
        """
        try:
            await check_pipeline_busy_or_raise(rag)
            result = await rag.aedit_entity(
                entity_name=request.entity_name,
                updated_data=request.updated_data,
                allow_rename=request.allow_rename,
                allow_merge=request.allow_merge,
            )

            # Extract operation_summary from result, with fallback for backward compatibility
            operation_summary = result.get(
                "operation_summary",
                {
                    "merged": False,
                    "merge_status": "not_attempted",
                    "merge_error": None,
                    "operation_status": "success",
                    "target_entity": None,
                    "final_entity": request.updated_data.get(
                        "entity_name", request.entity_name
                    ),
                    "renamed": request.updated_data.get(
                        "entity_name", request.entity_name
                    )
                    != request.entity_name,
                },
            )

            # Separate entity data from operation_summary for clean response
            entity_data = dict(result)
            entity_data.pop("operation_summary", None)

            # Generate appropriate response message based on merge status
            response_message = (
                f"Entity merged successfully into '{operation_summary['final_entity']}'"
                if operation_summary.get("merged")
                else "Entity updated successfully"
            )
            return {
                "status": "success",
                "message": response_message,
                "data": entity_data,
                "operation_summary": operation_summary,
            }
        except HTTPException:
            raise
        except ValueError as ve:
            logger.error(
                f"Validation error updating entity '{request.entity_name}': {str(ve)}"
            )
            raise HTTPException(status_code=400, detail=str(ve))
        except Exception as e:
            logger.error(f"Error updating entity '{request.entity_name}': {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500, detail=f"Error updating entity: {str(e)}"
            )

    @router.post("/graph/relation/edit", dependencies=[Depends(combined_auth)])
    async def update_relation(request: RelationUpdateRequest):
        """Update a relation's properties in the knowledge graph

        Args:
            request (RelationUpdateRequest): Request containing source ID, target ID and updated data

        Returns:
            Dict: Updated relation information
        """
        try:
            await check_pipeline_busy_or_raise(rag)
            result = await rag.aedit_relation(
                source_entity=request.source_id,
                target_entity=request.target_id,
                updated_data=request.updated_data,
            )
            return {
                "status": "success",
                "message": "Relation updated successfully",
                "data": result,
            }
        except HTTPException:
            raise
        except ValueError as ve:
            logger.error(
                f"Validation error updating relation between '{request.source_id}' and '{request.target_id}': {str(ve)}"
            )
            raise HTTPException(status_code=400, detail=str(ve))
        except Exception as e:
            logger.error(
                f"Error updating relation between '{request.source_id}' and '{request.target_id}': {str(e)}"
            )
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500, detail=f"Error updating relation: {str(e)}"
            )

    @router.post("/graph/entity/create", dependencies=[Depends(combined_auth)])
    async def create_entity(request: EntityCreateRequest):
        """
        Create a new entity in the knowledge graph

        This endpoint creates a new entity node in the knowledge graph with the specified
        properties. The system automatically generates vector embeddings for the entity
        to enable semantic search and retrieval.

        Request Body:
            entity_name (str): Unique name identifier for the entity
            entity_data (dict): Entity properties including:
                - description (str): Textual description of the entity
                - entity_type (str): Category/type of the entity (e.g., PERSON, ORGANIZATION, LOCATION)
                - source_id (str): Related chunk_id from which the description originates
                - Additional custom properties as needed

        Response Schema:
            {
                "status": "success",
                "message": "Entity 'Tesla' created successfully",
                "data": {
                    "entity_name": "Tesla",
                    "description": "Electric vehicle manufacturer",
                    "entity_type": "ORGANIZATION",
                    "source_id": "chunk-123<SEP>chunk-456"
                    ... (other entity properties)
                }
            }

        HTTP Status Codes:
            200: Entity created successfully
            400: Invalid request (e.g., missing required fields, duplicate entity)
            500: Internal server error

        Example Request:
            POST /graph/entity/create
            {
                "entity_name": "Tesla",
                "entity_data": {
                    "description": "Electric vehicle manufacturer",
                    "entity_type": "ORGANIZATION"
                }
            }
        """
        try:
            await check_pipeline_busy_or_raise(rag)
            # Use the proper acreate_entity method which handles:
            # - Graph lock for concurrency
            # - Vector embedding creation in entities_vdb
            # - Metadata population and defaults
            # - Index consistency via _edit_entity_done
            result = await rag.acreate_entity(
                entity_name=request.entity_name,
                entity_data=request.entity_data,
            )

            return {
                "status": "success",
                "message": f"Entity '{request.entity_name}' created successfully",
                "data": result,
            }
        except HTTPException:
            raise
        except ValueError as ve:
            logger.error(
                f"Validation error creating entity '{request.entity_name}': {str(ve)}"
            )
            raise HTTPException(status_code=400, detail=str(ve))
        except Exception as e:
            logger.error(f"Error creating entity '{request.entity_name}': {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500, detail=f"Error creating entity: {str(e)}"
            )

    @router.post("/graph/relation/create", dependencies=[Depends(combined_auth)])
    async def create_relation(request: RelationCreateRequest):
        """
        Create a new relationship between two entities in the knowledge graph

        This endpoint establishes an undirected relationship between two existing entities.
        The provided source/target order is accepted for convenience, but the backend
        stored edge is undirected and may be returned with the entities swapped.
        Both entities must already exist in the knowledge graph. The system automatically
        generates vector embeddings for the relationship to enable semantic search and graph traversal.

        Prerequisites:
            - Both source_entity and target_entity must exist in the knowledge graph
            - Use /graph/entity/create to create entities first if they don't exist

        Request Body:
            source_entity (str): Name of the source entity (relationship origin)
            target_entity (str): Name of the target entity (relationship destination)
            relation_data (dict): Relationship properties including:
                - description (str): Textual description of the relationship
                - keywords (str): Comma-separated keywords describing the relationship type
                - source_id (str): Related chunk_id from which the description originates
                - weight (float): Relationship strength/importance (default: 1.0)
                - Additional custom properties as needed

        Response Schema:
            {
                "status": "success",
                "message": "Relation created successfully between 'Elon Musk' and 'Tesla'",
                "data": {
                    "src_id": "Elon Musk",
                    "tgt_id": "Tesla",
                    "description": "Elon Musk is the CEO of Tesla",
                    "keywords": "CEO, founder",
                    "source_id": "chunk-123<SEP>chunk-456"
                    "weight": 1.0,
                    ... (other relationship properties)
                }
            }

        HTTP Status Codes:
            200: Relationship created successfully
            400: Invalid request (e.g., missing entities, invalid data, duplicate relationship)
            500: Internal server error

        Example Request:
            POST /graph/relation/create
            {
                "source_entity": "Elon Musk",
                "target_entity": "Tesla",
                "relation_data": {
                    "description": "Elon Musk is the CEO of Tesla",
                    "keywords": "CEO, founder",
                    "weight": 1.0
                }
            }
        """
        try:
            await check_pipeline_busy_or_raise(rag)
            # Use the proper acreate_relation method which handles:
            # - Graph lock for concurrency
            # - Entity existence validation
            # - Duplicate relation checks
            # - Vector embedding creation in relationships_vdb
            # - Index consistency via _edit_relation_done
            result = await rag.acreate_relation(
                source_entity=request.source_entity,
                target_entity=request.target_entity,
                relation_data=request.relation_data,
            )

            return {
                "status": "success",
                "message": f"Relation created successfully between '{request.source_entity}' and '{request.target_entity}'",
                "data": result,
            }
        except HTTPException:
            raise
        except ValueError as ve:
            logger.error(
                f"Validation error creating relation between '{request.source_entity}' and '{request.target_entity}': {str(ve)}"
            )
            raise HTTPException(status_code=400, detail=str(ve))
        except Exception as e:
            logger.error(
                f"Error creating relation between '{request.source_entity}' and '{request.target_entity}': {str(e)}"
            )
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500, detail=f"Error creating relation: {str(e)}"
            )

    @router.post("/graph/entities/merge", dependencies=[Depends(combined_auth)])
    async def merge_entities(request: EntityMergeRequest):
        """
        Merge multiple entities into a single entity, preserving all relationships

        This endpoint consolidates duplicate or misspelled entities while preserving the entire
        graph structure. It's particularly useful for cleaning up knowledge graphs after document
        processing or correcting entity name variations.

        What the Merge Operation Does:
            1. Deletes the specified source entities from the knowledge graph
            2. Transfers all relationships from source entities to the target entity
            3. Intelligently merges duplicate relationships (if multiple sources have the same relationship)
            4. Updates vector embeddings for accurate retrieval and search
            5. Preserves the complete graph structure and connectivity
            6. Maintains relationship properties and metadata

        Use Cases:
            - Fixing spelling errors in entity names (e.g., "Elon Msk" -> "Elon Musk")
            - Consolidating duplicate entities discovered after document processing
            - Merging name variations (e.g., "NY", "New York", "New York City")
            - Cleaning up the knowledge graph for better query performance
            - Standardizing entity names across the knowledge base

        Request Body:
            entities_to_change (list[str]): List of entity names to be merged and deleted
            entity_to_change_into (str): Target entity that will receive all relationships

        Response Schema:
            {
                "status": "success",
                "message": "Successfully merged 2 entities into 'Elon Musk'",
                "data": {
                    "merged_entity": "Elon Musk",
                    "deleted_entities": ["Elon Msk", "Ellon Musk"],
                    "relationships_transferred": 15,
                    ... (merge operation details)
                }
            }

        HTTP Status Codes:
            200: Entities merged successfully
            400: Invalid request (e.g., empty entity list, target entity doesn't exist)
            500: Internal server error

        Example Request:
            POST /graph/entities/merge
            {
                "entities_to_change": ["Elon Msk", "Ellon Musk"],
                "entity_to_change_into": "Elon Musk"
            }

        Note:
            - The target entity (entity_to_change_into) must exist in the knowledge graph
            - Source entities will be permanently deleted after the merge
            - This operation cannot be undone, so verify entity names before merging
        """
        try:
            await check_pipeline_busy_or_raise(rag)
            result = await rag.amerge_entities(
                source_entities=request.entities_to_change,
                target_entity=request.entity_to_change_into,
            )
            return {
                "status": "success",
                "message": f"Successfully merged {len(request.entities_to_change)} entities into '{request.entity_to_change_into}'",
                "data": result,
            }
        except HTTPException:
            raise
        except ValueError as ve:
            logger.error(
                f"Validation error merging entities {request.entities_to_change} into '{request.entity_to_change_into}': {str(ve)}"
            )
            raise HTTPException(status_code=400, detail=str(ve))
        except Exception as e:
            logger.error(
                f"Error merging entities {request.entities_to_change} into '{request.entity_to_change_into}': {str(e)}"
            )
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500, detail=f"Error merging entities: {str(e)}"
            )

    # --- entity casing/whitespace dedup (spec 013) -----------------------------------------------
    _DEDUP_STATUS_PATH = Path(
        os.getenv("DEDUP_STATUS_DIR", "/app/data/maintenance")
    ) / "dedup-status.json"

    async def _build_dedup_plan():
        """Pull the whole live graph and plan the casing/whitespace merges (pure planner does the rest)."""
        kg = await rag.get_knowledge_graph(node_label="*", max_depth=1, max_nodes=1_000_000)
        degree: Counter = Counter()
        for e in kg.edges:
            degree[e.source] += 1
            degree[e.target] += 1
        nodes = []
        for n in kg.nodes:
            name = n.properties.get("entity_id") or n.id
            raw = n.properties.get("concept_ref")
            try:
                cref = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                cref = None
            nodes.append(NodeView(name=name, concept_ref=cref, degree=degree.get(n.id, 0)))
        return plan_dedup(nodes)

    def _dedup_summary(plan) -> dict:
        return {
            "clusters": len(plan.merges) + len(plan.conflicts),
            "merges": len(plan.merges),
            "collapsible": plan.collapsible,
            "conflicts": len(plan.conflicts),
            "conflict_sample": [
                {"names": c.names, "codes": c.codes} for c in plan.conflicts[:25]
            ],
        }

    async def _run_dedup(plan):
        """Apply the merge plan via amerge_entities (background). Idempotent: a re-run finds ~0 clusters."""
        _DEDUP_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)

        def _write(state: dict):
            # stamp a heartbeat so a "running" left stale by a container restart is recoverable (see guard)
            _DEDUP_STATUS_PATH.write_text(json.dumps({**state, "ts": time.time()}), encoding="utf-8")

        total = len(plan.merges)
        _write({"state": "running", "merged": 0, "total": total})
        merged = failed = 0
        for m in plan.merges:
            try:
                # amerge_entities merges concept_ref with keep_first over [sources…, target], so the
                # survivor would inherit a SOURCE's ref, not the reconciled most-specific one — stamp it.
                target_data = {"concept_ref": json.dumps(m.ref, ensure_ascii=False)} if m.ref else None
                await rag.amerge_entities(
                    source_entities=m.sources,
                    target_entity=m.survivor,
                    target_entity_data=target_data,
                )
                merged += 1
            except Exception as e:  # noqa: BLE001 — one bad cluster must not abort the pass
                failed += 1
                logger.warning(f"dedup: merge into '{m.survivor}' failed: {e}")
            # heartbeat every 10 (small enough that a live run's gap stays well under the stale threshold,
            # even during slow hub merges)
            if (merged + failed) % 10 == 0:
                _write({"state": "running", "merged": merged, "failed": failed, "total": total})
        _write(
            {
                "state": "done",
                "merged": merged,
                "failed": failed,
                "total": total,
                "conflicts_skipped": len(plan.conflicts),
            }
        )
        logger.info(f"dedup: done — merged={merged} failed={failed} conflicts_skipped={len(plan.conflicts)}")

    @router.post("/graph:dedup", dependencies=[Depends(combined_auth)])
    async def graph_dedup(background_tasks: BackgroundTasks, apply: bool = Query(False)):
        """Collapse casing/whitespace/diacritic duplicate entity nodes (spec 013).

        ``apply=false`` (default) is a DRY-RUN: pull the graph, plan the merges, return counts + the
        conflict sample — no mutation. ``apply=true`` runs the merges in the background (poll
        ``GET /graph:dedup/status``); code-conflict clusters are always skipped, never auto-merged.
        """
        try:
            plan = await _build_dedup_plan()
            summary = _dedup_summary(plan)
            if not apply:
                summary["dry_run"] = True
                summary["merge_sample"] = [
                    {"survivor": m.survivor, "sources": m.sources} for m in plan.merges[:25]
                ]
                return summary
            await check_pipeline_busy_or_raise(rag)  # do not dedup mid-ingest
            # Refuse a concurrent apply — but only if a run is genuinely LIVE. A run left "running" by a
            # container restart (e.g. a redeploy mid-run) has a stale heartbeat; treat it as dead so the
            # (idempotent) pass can be resumed instead of being wedged forever.
            _DEDUP_STALE_S = float(os.getenv("DEDUP_STALE_SECONDS", "600"))
            if _DEDUP_STATUS_PATH.exists():
                try:
                    st = json.loads(_DEDUP_STATUS_PATH.read_text(encoding="utf-8"))
                    if st.get("state") == "running" and (time.time() - float(st.get("ts", 0))) < _DEDUP_STALE_S:
                        raise HTTPException(status_code=409, detail="a dedup apply run is already in progress")
                except HTTPException:
                    raise
                except Exception:  # noqa: BLE001 — unreadable status ⇒ treat as not-running
                    pass
            background_tasks.add_task(_run_dedup, plan)
            return {"status": "started", "status_url": "/graph:dedup/status", **summary}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"graph:dedup error: {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"graph:dedup error: {str(e)}")

    @router.get("/graph:dedup/status", dependencies=[Depends(combined_auth)])
    async def graph_dedup_status():
        """State of the latest dedup apply run (none/running/done)."""
        if not _DEDUP_STATUS_PATH.exists():
            return {"state": "none"}
        try:
            return json.loads(_DEDUP_STATUS_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {"state": "unknown"}

    # --- _unknown edition-year rename (spec 016) -------------------------------------------------
    _RENAME_STATUS_PATH = Path(
        os.getenv("DEDUP_STATUS_DIR", "/app/data/maintenance")
    ) / "rename-edition-status.json"

    # file_path persistence sites (postgres_impl DDL). Chunk tables = single-valued + load-bearing (the
    # chunk registry + chat references read these → edition ordering). Substring = `<SEP>`-joined + capped
    # provenance (source chips), display-only, best-effort. LIGHTRAG_DOC_STATUS is handled LAST, on its own
    # (see _run_rename): it is the plan source, so leaving it until every other store is renamed means a
    # partial failure re-plans the doc on the next run and the idempotent ops safely finish it.
    _RENAME_CHUNK_TABLES = ("LIGHTRAG_DOC_CHUNKS", "LIGHTRAG_VDB_CHUNKS")
    _RENAME_SUBSTR_TABLES = ("LIGHTRAG_VDB_ENTITY", "LIGHTRAG_VDB_RELATION")

    async def _live_doc_file_paths():
        """Distinct doc file_paths in the store (drives the dry-run plan)."""
        db = rag.doc_status.db
        ws = rag.doc_status.workspace
        rows = await db.query(
            "SELECT DISTINCT file_path FROM LIGHTRAG_DOC_STATUS "
            "WHERE workspace=$1 AND file_path IS NOT NULL",
            [ws],
            multirows=True,
        )
        return [r["file_path"] for r in (rows or [])]

    async def _run_rename(plan):
        """Apply the file_path renames (background). Idempotent: a re-run plans 0."""
        _RENAME_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)

        def _write(state: dict):
            _RENAME_STATUS_PATH.write_text(
                json.dumps({**state, "ts": time.time()}), encoding="utf-8"
            )

        db = rag.doc_status.db
        ws = rag.doc_status.workspace
        graph = rag.chunk_entity_relation_graph

        async def _existing(tables):
            """Keep only tables present in this deployment. Some stores predate the DOC_CHUNKS→VDB_CHUNKS
            split (chunk vectors still live in LIGHTRAG_DOC_CHUNKS) or lack the VDB entity/relation tables;
            UPDATEing a missing table would abort the doc, so filter up-front instead."""
            out = []
            for t in tables:
                row = await db.query("SELECT to_regclass($1) IS NOT NULL AS present", [t.lower()])
                if row and row.get("present"):
                    out.append(t)
                else:
                    logger.info(f"rename-edition: table {t} absent in this store — skipping")
            return out

        chunk_tables = await _existing(_RENAME_CHUNK_TABLES)
        substr_tables = await _existing(_RENAME_SUBSTR_TABLES)

        # concrete work items: BOTH unicode normalizations of every known (old -> new). Stores disagree
        # on NFC vs NFD (PG is NFD from the macOS-decomposed ingest; some Neo4j nodes are NFC), so a
        # single-form match misses the other. Every op is idempotent (no-op when the substring is absent),
        # so sweeping all variants also mops up residue a prior single-form run left in a store whose
        # doc_status is already renamed (the doc_status-sourced plan would otherwise report nothing to do).
        work: set[tuple[str, str]] = set()
        for old_nfc, year in EDITION_YEARS.items():
            new_nfc = _new_name(old_nfc, year)
            for norm in ("NFC", "NFD"):
                work.add((unicodedata.normalize(norm, old_nfc), unicodedata.normalize(norm, new_nfc)))
        work.update(plan.to_rename)  # stored spellings the plan matched, in case of an unforeseen form

        total = len(work)
        _write({"state": "running", "processed": 0, "total": total, "tables": chunk_tables + substr_tables})
        processed = failed = 0
        label = graph._get_workspace_label()
        # every UPDATE uses the SAME param dict {old, new, ws} → $1=old, $2=new, $3=ws — one convention
        # across whole-value and substring so a copy-edit can't silently swap old↔new.
        for old, new in work:
            try:
                # PG chunk-level whole-value (load-bearing: edition ordering reads these)
                for tbl in chunk_tables:
                    await db.execute(
                        f"UPDATE {tbl} SET file_path=$2 WHERE file_path=$1 AND workspace=$3",
                        {"old": old, "new": new, "ws": ws},
                    )
                # PG substring (provenance: `<SEP>`-joined; strpos avoids `_` being a LIKE wildcard)
                for tbl in substr_tables:
                    await db.execute(
                        f"UPDATE {tbl} SET file_path=REPLACE(file_path,$1,$2) "
                        f"WHERE strpos(file_path,$1)>0 AND workspace=$3",
                        {"old": old, "new": new, "ws": ws},
                    )
                # Neo4j node + relationship file_path (scoped to the workspace label)
                async with graph._driver.session(database=graph._DATABASE) as session:
                    await session.run(
                        f"MATCH (n:`{label}`) WHERE n.file_path CONTAINS $old "
                        f"SET n.file_path = replace(n.file_path, $old, $new)",
                        old=old,
                        new=new,
                    )
                    await session.run(
                        f"MATCH (:`{label}`)-[r]->() WHERE r.file_path CONTAINS $old "
                        f"SET r.file_path = replace(r.file_path, $old, $new)",
                        old=old,
                        new=new,
                    )
                # DOC_STATUS (the doc listing / plan source)
                await db.execute(
                    "UPDATE LIGHTRAG_DOC_STATUS SET file_path=$2 WHERE file_path=$1 AND workspace=$3",
                    {"old": old, "new": new, "ws": ws},
                )
                processed += 1
            except Exception as e:  # noqa: BLE001 — one bad variant must not abort the pass
                failed += 1
                logger.warning(f"rename-edition: '{old}' -> '{new}' failed: {e}")
            _write({"state": "running", "processed": processed, "failed": failed, "total": total})

        # spec 020: reconcile the on-volume parsed artifacts to the renamed edition. The metadata rename above
        # left each doc's `<work>_unknown.pdf.parsed` dir untouched, so the read-path resolver (derives the dir
        # from the renamed `_<year>` file_path) can't load blocks.jsonl → page/section resolve None. Move the
        # archived PDF + .parsed + .mineru_raw siblings and keep DOC_FULL.sidecar_location pointing at the moved
        # .parsed dir. Best-effort + idempotent: never aborts the DB rename that already succeeded.
        fs_renamed = 0
        for old_p, new_p in parsed_artifact_renames(parsed_dir()):
            is_parsed = new_p.name.endswith(".parsed")
            old_uri, new_uri = (sidecar_uri_for(old_p), sidecar_uri_for(new_p)) if is_parsed else (None, None)
            try:
                os.rename(old_p, new_p)
                fs_renamed += 1
                if is_parsed:
                    await db.execute(
                        "UPDATE LIGHTRAG_DOC_FULL SET sidecar_location=$2 "
                        "WHERE sidecar_location=$1 AND workspace=$3",
                        {"old": old_uri, "new": new_uri, "ws": ws},
                    )
            except Exception as e:  # noqa: BLE001 — one bad rename must not abort the pass
                logger.warning(f"rename-edition: parsed-artifact '{old_p}' -> '{new_p}' failed: {e}")
        if fs_renamed:
            logger.info(f"rename-edition: reconciled {fs_renamed} on-volume parsed artifact(s)")

        _write({"state": "done", "processed": processed, "failed": failed, "total": total})
        logger.info(f"rename-edition: done — processed={processed} failed={failed} total={total}")

    @router.post("/graph:rename-edition", dependencies=[Depends(combined_auth)])
    async def graph_rename_edition(background_tasks: BackgroundTasks, apply: bool = Query(False)):
        """Rename the spec-016 `_unknown` docs to their verified edition year (fix supersession-inversion).

        ``apply=false`` (default) is a DRY-RUN: plan which docs rename vs are already done — no mutation.
        ``apply=true`` runs the renames in the background (poll ``GET /graph:rename-edition/status``).
        Idempotent: once a doc carries its `_<year>` name a re-run plans 0.
        """
        try:
            live = await _live_doc_file_paths()
            plan = plan_rename(live)
            summary = plan.summary()
            if not apply:
                summary["dry_run"] = True
                return summary
            # apply always runs the full variant sweep (not gated on plan.count): a doc can be renamed in
            # doc_status yet still carry `_unknown` in another store (Neo4j NFC nodes), which the sweep
            # cleans. Idempotent, so a truly-clean store just performs no-op UPDATEs.
            await check_pipeline_busy_or_raise(rag)  # do not rename mid-ingest
            _RENAME_STALE_S = float(os.getenv("DEDUP_STALE_SECONDS", "600"))
            if _RENAME_STATUS_PATH.exists():
                try:
                    st = json.loads(_RENAME_STATUS_PATH.read_text(encoding="utf-8"))
                    if st.get("state") == "running" and (time.time() - float(st.get("ts", 0))) < _RENAME_STALE_S:
                        raise HTTPException(status_code=409, detail="a rename-edition apply run is already in progress")
                except HTTPException:
                    raise
                except Exception:  # noqa: BLE001 — unreadable status ⇒ treat as not-running
                    pass
            background_tasks.add_task(_run_rename, plan)
            return {"status": "started", "status_url": "/graph:rename-edition/status", **summary}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"graph:rename-edition error: {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"graph:rename-edition error: {str(e)}")

    @router.get("/graph:rename-edition/status", dependencies=[Depends(combined_auth)])
    async def graph_rename_edition_status():
        """State of the latest rename-edition apply run (none/running/done)."""
        if not _RENAME_STATUS_PATH.exists():
            return {"state": "none"}
        try:
            return json.loads(_RENAME_STATUS_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {"state": "unknown"}

    @router.delete(
        "/graph/entity/delete",
        response_model=DeletionResult,
        dependencies=[Depends(combined_auth)],
    )
    async def delete_entity(request: DeleteEntityRequest):
        """
        Delete an entity and all its relationships from the knowledge graph.

        Args:
            request (DeleteEntityRequest): The request body containing the entity name.

        Returns:
            DeletionResult: An object containing the outcome of the deletion process.

        Raises:
            HTTPException: If the entity is not found (404) or an error occurs (500).
        """
        try:
            await check_pipeline_busy_or_raise(rag)
            result = await rag.adelete_by_entity(entity_name=request.entity_name)
            if result.status == "not_found":
                raise HTTPException(status_code=404, detail=result.message)
            if result.status == "fail":
                raise HTTPException(status_code=500, detail=result.message)
            # Set doc_id to empty string since this is an entity operation, not document
            result.doc_id = ""
            return result
        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"Error deleting entity '{request.entity_name}': {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=error_msg)

    @router.delete(
        "/graph/relation/delete",
        response_model=DeletionResult,
        dependencies=[Depends(combined_auth)],
    )
    async def delete_relation(request: DeleteRelationRequest):
        """
        Delete a relationship between two entities from the knowledge graph.

        Args:
            request (DeleteRelationRequest): The request body containing the source and target entity names.

        Returns:
            DeletionResult: An object containing the outcome of the deletion process.

        Raises:
            HTTPException: If the relation is not found (404) or an error occurs (500).
        """
        try:
            await check_pipeline_busy_or_raise(rag)
            result = await rag.adelete_by_relation(
                source_entity=request.source_entity,
                target_entity=request.target_entity,
            )
            if result.status == "not_found":
                raise HTTPException(status_code=404, detail=result.message)
            if result.status == "fail":
                raise HTTPException(status_code=500, detail=result.message)
            # Set doc_id to empty string since this is a relation operation, not document
            result.doc_id = ""
            return result
        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"Error deleting relation from '{request.source_entity}' to '{request.target_entity}': {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=error_msg)

    return router
