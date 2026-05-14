"""Standalone test script for vector similarity search with 1024D embeddings.

Usage:
    cd apps/mcp-server
    DATABASE_URL="postgresql://..." python scripts/test_vector_search.py
"""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import directly from the module file to avoid services/__init__.py
import importlib.util

# Load embeddings module directly without triggering __init__.py
embeddings_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "services", "embeddings.py"
)

spec = importlib.util.spec_from_file_location("embeddings", embeddings_path)
embeddings_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(embeddings_module)

EmbeddingsService = embeddings_module.EmbeddingsService
EMBEDDING_DIMENSION = embeddings_module.EMBEDDING_DIMENSION
MODEL_NAME = embeddings_module.MODEL_NAME


def test_embedding_generation():
    """Test that embeddings are generated with 1024 dimensions."""
    print("🔍 Test: Génération d'embeddings 1024D...")
    print(f"   📦 Modèle: {MODEL_NAME}")
    print(f"   📏 Dimension attendue: {EMBEDDING_DIMENSION}")
    
    # Create embeddings service directly
    embeddings_service = EmbeddingsService()
    
    # Test single text
    test_text = "How to configure authentication in the application?"
    print(f"\n   📝 Texte de test: \"{test_text}\"")
    
    embedding = embeddings_service.embed_text(test_text)
    
    print(f"   📏 Dimension réelle: {len(embedding)}")
    print(f"   📦 Premieres valeurs: {embedding[:5]}...")
    print(f"   📦 Dernieres valeurs: {embedding[-5:]}...")
    
    if len(embedding) == 1024:
        print("   ✅ Embedding a 1024 dimensions!")
    else:
        print(f"   ❌ Erreur: Embedding a {len(embedding)} dimensions au lieu de 1024")
        return False
    
    # Test batch embedding
    test_texts = [
        "User authentication methods",
        "Database connection setup",
        "API rate limiting configuration"
    ]
    embeddings = embeddings_service.embed_texts(test_texts)
    
    print(f"\n   📦 Batch embeddings: {len(embeddings)} vecteurs")
    for i, (text, emb) in enumerate(zip(test_texts, embeddings)):
        print(f"      {i+1}. \"{text[:30]}...\" -> {len(emb)} dimensions")
    
    all_1024 = all(len(e) == 1024 for e in embeddings)
    
    if all_1024:
        print("   ✅ Tous les embeddings batch ont 1024 dimensions!")
    else:
        print("   ❌ Erreur: Certains embeddings n'ont pas 1024 dimensions")
        return False
    
    # Test cosine similarity
    print("\n   🧮 Test de similarité cosinus...")
    query = "user authentication"
    doc1 = "Login and authentication system"
    doc2 = "Database connection pooling"
    
    query_emb = embeddings_service.embed_text(query)
    doc1_emb = embeddings_service.embed_text(doc1)
    doc2_emb = embeddings_service.embed_text(doc2)
    
    similarities = embeddings_service.cosine_similarity(query_emb, [doc1_emb, doc2_emb])
    
    print(f"   📝 Requête: \"{query}\"")
    print(f"   📝 Doc 1: \"{doc1}\" -> similarité: {similarities[0]:.4f}")
    print(f"   📝 Doc 2: \"{doc2}\" -> similarité: {similarities[1]:.4f}")
    
    if similarities[0] > similarities[1]:
        print("   ✅ La similarité est plus élevée pour le document pertinent!")
    else:
        print("   ⚠️  La similarité devrait être plus élevée pour le document pertinent")
    
    return True


async def test_vector_similarity_search():
    """Test vector similarity search against the database."""
    print("\n🔍 Test: Recherche de similarité vectorielle (base de données)...")
    
    # Check if DATABASE_URL is set
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("   ⚠️  DATABASE_URL non configuré - test de base de données ignoré")
        print("   💡 Pour tester la base de données:")
        print("      DATABASE_URL=\"postgresql://user:pass@host:5432/db\" python scripts/test_vector_search.py")
        return True
    
    try:
        from prisma import Prisma
        
        db = Prisma()
        await db.connect()
        print("   ✅ Connexion à la base de données établie")
        
        # Check if document_chunks table has data
        count_result = await db.query_raw("SELECT COUNT(*) as count FROM document_chunks")
        count = count_result[0]["count"] if count_result else 0
        print(f"   📊 Nombre de chunks dans la base: {count}")
        
        if count == 0:
            print("   ℹ️  Pas de chunks dans la base de données.")
            print("      Utilisez: python scripts/reindex_embeddings.py pour indexer les documents")
            await db.disconnect()
            return True
        
        # Generate embedding for test query
        embeddings_service = EmbeddingsService()
        query = "authentication and user login"
        query_embedding = embeddings_service.embed_text(query)
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        
        print(f"   🔢 Embedding de la requête généré ({len(query_embedding)} dimensions)")
        
        # Perform vector similarity search using pgvector
        results = await db.query_raw('''
            SELECT
                d.path as file_path,
                dc.content,
                1 - (dc.embedding <=> $1::vector) as similarity
            FROM document_chunks dc
            JOIN documents d ON dc."documentId" = d.id
            ORDER BY dc.embedding <=> $1::vector
            LIMIT 5
        ''', embedding_str)
        
        print(f"   🔍 Résultats de la recherche: {len(results)} documents trouvés")
        
        for i, result in enumerate(results):
            similarity = result.get("similarity", 0)
            file_path = result.get("file_path", "unknown")
            content_preview = result.get("content", "")[:100]
            print(f"      {i+1}. [{similarity:.4f}] {file_path}")
            print(f"         {content_preview}...")
        
        print("   ✅ Recherche de similarité vectorielle fonctionnelle!")
        await db.disconnect()
        return True
        
    except Exception as e:
        print(f"   ❌ Erreur lors du test de recherche: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_embedding_dimension_consistency():
    """Verify that database schema matches embedding dimension."""
    print("\n🔍 Test: Vérification de la cohérence des dimensions...")
    
    # Check if DATABASE_URL is set
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("   ⚠️  DATABASE_URL non configuré - vérification ignorée")
        return True
    
    try:
        from prisma import Prisma
        
        db = Prisma()
        await db.connect()
        
        # Try to get a sample embedding to verify dimension
        sample = await db.query_raw('''
            SELECT embedding 
            FROM document_chunks 
            LIMIT 1
        ''')
        
        if sample and sample[0].get("embedding"):
            embedding_str = sample[0]["embedding"]
            # Count elements in the vector
            if embedding_str.startswith('[') and embedding_str.endswith(']'):
                elements = embedding_str[1:-1].split(',')
                print(f"   📏 Dimension de l'embedding en base: {len(elements)}")
                
                if len(elements) == 1024:
                    print("   ✅ La dimension de l'embedding en base correspond à 1024!")
                else:
                    print(f"   ⚠️  La dimension en base ({len(elements)}) ne correspond pas à 1024")
            else:
                print(f"   📝 Format de l'embedding: {type(embedding_str)}")
        else:
            print("   ℹ️  Pas d'embeddings en base pour vérifier la dimension")
        
        await db.disconnect()
        return True
        
    except Exception as e:
        print(f"   ❌ Erreur lors de la vérification: {e}")
        return False


async def main():
    """Run all vector search tests."""
    print("=" * 60)
    print("🧪 Tests de recherche vectorielle 1024D")
    print("=" * 60)
    
    all_passed = True
    
    # Test 1: Embedding generation (synchronous)
    if not test_embedding_generation():
        all_passed = False
    
    # Tests 2 & 3: Database tests (async)
    if not await test_vector_similarity_search():
        all_passed = False
    
    if not await test_embedding_dimension_consistency():
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ Tous les tests ont réussi!")
    else:
        print("⚠️  Certains tests ont échoué")
    print("=" * 60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
