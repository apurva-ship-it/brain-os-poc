from fastapi import APIRouter, UploadFile, File, Form
from services import p4_knowledge

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/stats")
async def knowledge_stats():
    return p4_knowledge.get_stats()


@router.post("/upload")
async def upload_document(
    brand_id: str = Form(...),
    section: str = Form("Uploaded Document"),
    dataset: str = Form("brand_knowledge"),
    file: UploadFile = File(...),
):
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")
    total = p4_knowledge.add_document(brand_id, text, section, dataset)
    return {
        "status": "ingested",
        "brand_id": brand_id,
        "section": section,
        "dataset": dataset,
        "chars": len(text),
        "total_chunks": total,
    }


@router.post("/ingest-text")
async def ingest_text(brand_id: str, text: str, section: str = "Custom Document", dataset: str = "brand_knowledge"):
    total = p4_knowledge.add_document(brand_id, text, section, dataset)
    return {"status": "ingested", "brand_id": brand_id, "total_chunks": total}
