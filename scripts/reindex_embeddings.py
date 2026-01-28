#!/usr/bin/env python3
"""
Script de réindexation des embeddings vers 1024 dimensions (bge-large-en-v1.5)

Usage:
    python scripts/reindex_embeddings.py

Options:
    --clear    Supprimer les embeddings existants avant réindexation
    --project  ID du projet spécifique à réindexer (par défaut: tous)
"""

import asyncio
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from services.indexer import DocumentIndexer
from services.embeddings import get_embeddings_service
from db import get_db


async def reindex_all_documents(project_id: str = None):
    """Réindexer tous les documents avec le nouveau modèle d'embeddings."""
    print("🚀 Début de la réindexation vers 1024 dimensions...")
    
    db = await get_db()
    indexer = DocumentIndexer(db)
    embeddings = get_embeddings_service()
    
    print(f"📦 Modèle: {embeddings.model_name}")
    print(f"📐 Dimension: {embeddings.dimension}")
    
    # Récupérer les projets
    where = {}
    if project_id:
        where["id"] = project_id
        projects = await db.project.find_many(where=where)
        if not projects:
            print(f"❌ Projet non trouvé: {project_id}")
            return
    else:
        projects = await db.project.find_many()
    
    print(f"📊 Projets à traiter: {len(projects)}")
    
    total_docs = 0
    total_chunks = 0
    
    for project in projects:
        print(f"\n🔄 {project.name} ({project.id})")
        
        documents = await db.document.find_many(
            where={"projectId": project.id}
        )
        print(f"   📄 {len(documents)} documents")
        
        project_chunks = 0
        for doc in documents:
            try:
                chunks = await indexer.index_document(doc.id)
                project_chunks += chunks
            except Exception as e:
                print(f"   ❌ {doc.path}: {e}")
        
        total_docs += len(documents)
        total_chunks += project_chunks
        print(f"   ✅ {project_chunks} chunks générés")
    
    print(f"\n✅ Terminé: {total_docs} docs, {total_chunks} chunks, {embeddings.dimension}D")


async def clear_all_embeddings():
    """Supprimer tous les embeddings."""
    print("🗑️ Suppression des embeddings...")
    db = await get_db()
    count = await db.query_raw("SELECT COUNT(*) FROM document_chunks")
    total = count[0]["count"] if count else 0
    await db.execute_raw("DELETE FROM document_chunks")
    print(f"   ✅ {total} embeddings supprimés")


async def main():
    parser = argparse.ArgumentParser(description="Réindexation embeddings 1024D")
    parser.add_argument("--clear", action="store_true", help="Supprimer avant réindexation")
    parser.add_argument("--project", type=str, help="Projet spécifique")
    args = parser.parse_args()
    
    if args.clear:
        await clear_all_embeddings()
    
    await reindex_all_documents(args.project)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    asyncio.run(main())
