"""Export routes — export search results and latest blocks as CSV or JSON."""

import csv
import io
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from aitbc.aitbc_logging import get_logger

from chain_client import get_latest_blocks

logger = get_logger(__name__)

router = APIRouter()


@router.get("/api/export/search")
async def export_search(format: str = "csv", type: str = "transactions", data: str = "") -> StreamingResponse:
    """Export search results"""
    try:
        if not data:
            raise HTTPException(status_code=400, detail="No data to export")

        results = json.loads(data)

        if format == "csv":
            output = io.StringIO()
            if type == "transactions":
                writer = csv.writer(output)
                writer.writerow(["Hash", "Type", "From", "To", "Amount", "Fee", "Timestamp"])
                for tx in results:
                    writer.writerow(
                        [
                            tx.get("hash", ""),
                            tx.get("type", ""),
                            tx.get("from", ""),
                            tx.get("to", ""),
                            tx.get("amount", ""),
                            tx.get("fee", ""),
                            tx.get("timestamp", ""),
                        ]
                    )
            else:  # blocks
                writer = csv.writer(output)
                writer.writerow(["Height", "Hash", "Validator", "Transactions", "Timestamp"])
                for block in results:
                    writer.writerow(
                        [
                            block.get("height", ""),
                            block.get("hash", ""),
                            block.get("validator", ""),
                            block.get("tx_count", ""),
                            block.get("timestamp", ""),
                        ]
                    )

            output.seek(0)
            return StreamingResponse(
                io.BytesIO(output.getvalue().encode()),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=search_results.{format}"},
            )

        elif format == "json":
            return StreamingResponse(
                io.BytesIO(json.dumps(results, indent=2).encode()),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename=search_results.{format}"},
            )

        else:
            raise HTTPException(status_code=400, detail="Unsupported format")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}") from e


@router.get("/api/export/blocks")
async def export_blocks(format: str = "csv") -> StreamingResponse:
    """Export latest blocks"""
    try:
        # Get latest blocks
        blocks = await get_latest_blocks(50)

        if format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Height", "Hash", "Validator", "Transactions", "Timestamp"])
            for block in blocks:
                writer.writerow(
                    [
                        block.get("height", ""),
                        block.get("hash", ""),
                        block.get("validator", ""),
                        block.get("tx_count", ""),
                        block.get("timestamp", ""),
                    ]
                )

            output.seek(0)
            return StreamingResponse(
                io.BytesIO(output.getvalue().encode()),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=latest_blocks.{format}"},
            )

        elif format == "json":
            return StreamingResponse(
                io.BytesIO(json.dumps(blocks, indent=2).encode()),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename=latest_blocks.{format}"},
            )

        else:
            raise HTTPException(status_code=400, detail="Unsupported format")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}") from e
