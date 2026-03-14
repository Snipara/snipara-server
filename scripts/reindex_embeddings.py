#!/usr/bin/env python3
"""
Script de réindexation des embeddings vers 1024 dimensions (bge-large-en-v1.5)

Ce script:
1. Supprime tous les embeddings existants
2. Génère de nouveaux embeddings 1024D pour tous les documents
3. Les insère dans la base de données

Usage:
    python scripts/reindex_embeddings.py
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import dotenv_values

# Load environment variables from project root and set them in os.environ
env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
# Fallback to absolute path if relative doesn't work
if not env_path.exists():
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        env_path = Path.home() / "Devs/Snipara/.env"
for key, value in dotenv_values(env_path).items():
    os.environ.setdefault(key, value)

# Add src parent dir to path (project root)
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.indexer import DocumentIndexer
from src.services.embeddings import get_embeddings_service
from src.db import get_db


async def reindex_all_documents():
    """Réindexer tous les documents avec le nouveau modèle d'embeddings."""
    print("🚀 Début de la réindexation vers 1024 dimensions...")
    
    db = await get_db()
    indexer = DocumentIndexer(db)
    embeddings = get_embeddings_service()
    
    # Vérifier le modèle
    print(f"📦 Modèle d'embeddings: {embeddings.model_name}")
    print(f"📐 Dimension: {embeddings.dimension}")
    
    # Récupérer tous les projets
    projects = await db.project.find_many()
    print(f"📊 Projets trouvés: {len(projects)}")
    
    total_docs = 0
    total_chunks = 0
    
    for project in projects:
        print(f"\n🔄 Traitement du projet: {project.name} ({project.id})")
        
        # Récupérer les documents du projet
        documents = await db.document.find_many(
            where={"projectId": project.id}
        )
        print(f"   📄 Documents: {len(documents)}")
        
        project_chunks = 0
        for doc in documents:
            try:
                chunks = await indexer.index_document(doc.id)
                project_chunks += chunks
                print(f"   ✅ {doc.path}: {chunks} chunks")
            except Exception as e:
                print(f"   ❌ Erreur pour {doc.path}: {e}")
        
        total_docs += len(documents)
        total_chunks += project_chunks
    
    print(f"\n✅ Réindexation terminée!")
    print(f"   Total documents: {total_docs}")
    print(f"   Total chunks: {total_chunks}")
    print(f"   Dimension des embeddings: {embeddings.dimension}")


async def clear_all_embeddings():
    """Supprimer tous les embeddings existants (utile si erreur de dimension)."""
    print("🗑️ Suppression de tous les embeddings...")
    
    db = await get_db()
    
    # Compter avant suppression
    count = await db.query_raw("SELECT COUNT(*) as count FROM document_chunks")
    total = count[0]["count"] if count else 0
    print(f"   Embeddings à supprimer: {total}")
    
    # Supprimer
    await db.execute_raw("DELETE FROM document_chunks")
    print(f"   ✅ {total} embeddings supprimés")


async def main():
    """Point d'entrée principal."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Réindexation des embeddings")
    parser.add_argument("--clear", action="store_true", help="Supprimer les embeddings existants avant réindexation")
    args = parser.parse_args()
    
    if args.clear:
        await clear_all_embeddings()
    
    await reindex_all_documents()


if __name__ == "__main__":
    asyncio.run(main())
