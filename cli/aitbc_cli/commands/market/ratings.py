"""
Rating commands: rate, ratings, sync-ratings
"""

import click

from ...utils import error, info, output, success
from ...utils.http_client import AITBCHTTPClient, NetworkError, get_logger

# Initialize logger
logger = get_logger(__name__)

from . import get_wallet_address, market


@market.command(name="rate")
@click.argument("service_id")
@click.argument("rating", type=float)
@click.option("--comment", help="Optional comment/review text")
@click.option("--reviewer-id", help="Reviewer ID (defaults to wallet address)")
@click.pass_context
def rate(ctx, service_id: str, rating: float, comment: str, reviewer_id: str):
    """Rate a marketplace service offer (1-5 scale)"""
    try:
        # Validate rating scale
        if not (1.0 <= rating <= 5.0):
            error("Rating must be between 1.0 and 5.0")
            raise click.Abort()

        # Default reviewer_id to wallet address
        if not reviewer_id:
            reviewer_id = get_wallet_address()

        # Call marketplace service API
        client = AITBCHTTPClient(base_url="http://localhost:8102", timeout=10)
        response = client.post(
            f"/v1/marketplace/offer/{service_id}/rate",
            json={"rating": rating, "reviewer_id": reviewer_id, "comment": comment or ""},
        )

        if response.get("status") == "success":
            rating_data = response.get("rating", {})
            success("Service rated successfully!")
            output(
                {
                    "service_id": rating_data.get("service_id"),
                    "rating": rating_data.get("rating"),
                    "reviewer_id": rating_data.get("reviewer_id"),
                    "comment": rating_data.get("comment"),
                    "created_at": rating_data.get("created_at"),
                },
                ctx.obj.get("output_format", "table"),
            )
        else:
            error(f"Failed to rate service: {response.get('message', 'Unknown error')}")
            output(response)
            raise click.Abort()

    except NetworkError as e:
        error(f"Marketplace service not reachable: {e}")
        error("Ensure marketplace-service is running at http://localhost:8102")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error rating service: {e}")
        raise click.Abort() from e


@market.command(name="ratings")
@click.argument("service_id")
@click.option("--limit", default=50, help="Number of ratings to return")
@click.option("--offset", default=0, help="Offset for pagination")
@click.pass_context
def ratings(ctx, service_id: str, limit: int, offset: int):
    """View ratings for a marketplace service offer"""
    try:
        # Call marketplace service API
        client = AITBCHTTPClient(base_url="http://localhost:8102", timeout=10)
        response = client.get(f"/v1/marketplace/offer/{service_id}/ratings", params={"limit": limit, "offset": offset})

        service_info = response.get("service_info", {})
        ratings_list = response.get("ratings", [])

        info(f"Service: {service_id}")
        info(f"Average Rating: {service_info.get('avg_rating', 0.0):.1f}/5.0")
        info(f"Total Ratings: {service_info.get('rating_count', 0)}")
        info(f"Showing {len(ratings_list)} ratings")

        if ratings_list:
            output(ratings_list, ctx.obj.get("output_format", "table"))
        else:
            info("No ratings found for this service")

    except NetworkError as e:
        error(f"Marketplace service not reachable: {e}")
        error("Ensure marketplace-service is running at http://localhost:8102")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error getting ratings: {e}")
        raise click.Abort() from e


@market.command(name="sync-ratings")
@click.option("--remote-url", default="https://aitbc3.aitbc.bubuit.net/api", help="Remote marketplace service URL")
@click.option("--limit", default=100, help="Number of ratings to sync")
@click.pass_context
def sync_ratings(ctx, remote_url: str, limit: int):
    """Sync ratings to/from remote marketplace node"""
    try:
        # Get local unsynced ratings
        local_client = AITBCHTTPClient(base_url="http://localhost:8102", timeout=10)
        unsynced_response = local_client.get("/v1/marketplace/ratings/unsynced", params={"limit": limit})
        unsynced_ratings = unsynced_response.get("ratings", [])

        if unsynced_ratings:
            info(f"Found {len(unsynced_ratings)} unsynced ratings to push to {remote_url}")

            # Push to remote
            remote_client = AITBCHTTPClient(base_url=remote_url, timeout=30)
            sync_response = remote_client.post("/v1/marketplace/ratings/sync", json=unsynced_ratings)

            if sync_response.get("status") == "success":
                # Mark local ratings as synced
                rating_ids = [r["id"] for r in unsynced_ratings]
                mark_response = local_client.post("/v1/marketplace/ratings/mark-synced", json=rating_ids)

                success(
                    f"Synced {sync_response.get('synced', 0)} new, {sync_response.get('updated', 0)} updated ratings to remote"
                )
                info(f"Marked {mark_response.get('marked_synced', 0)} local ratings as synced")
            else:
                error(f"Failed to sync ratings to remote: {sync_response}")
        else:
            info("No unsynced ratings found locally")

        # Pull remote ratings (optional - could be made a separate command)
        info("Rating sync complete")

    except NetworkError as e:
        error(f"Network error during sync: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error syncing ratings: {e}")
        raise click.Abort() from e
