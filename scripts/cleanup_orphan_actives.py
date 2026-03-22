"""
Script para limpar arquivos órfãos de ativos
Remove arquivos em data/actives que excedem o limite configurado
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Adicionar diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Carregar variáveis de ambiente
load_dotenv()

def cleanup_orphan_actives():
    """Remove arquivos de ativos que excedem o limite configurado"""
    
    # Ler configuração
    max_actives = int(os.getenv("MONITORING_ACTIVES_QUANTIDADE", "10"))
    data_dir = Path("data/actives")
    
    if not data_dir.exists():
        print(f"❌ Diretório {data_dir} não existe")
        return
    
    # Listar todos os arquivos
    files = list(data_dir.glob("*.txt"))
    total_files = len(files)
    
    print(f"📊 Configuração:")
    print(f"   - Máximo de ativos: {max_actives}")
    print(f"   - Arquivos encontrados: {total_files}")
    
    if total_files <= max_actives:
        print(f"✅ Número de arquivos ({total_files}) está dentro do limite ({max_actives})")
        return
    
    # Calcular quantos arquivos precisam ser removidos
    to_remove = total_files - max_actives
    print(f"\n⚠️  Excesso de {to_remove} arquivos detectado")
    
    # Listar arquivos por data de modificação (mais antigos primeiro)
    files_with_mtime = [(f, f.stat().st_mtime) for f in files]
    files_with_mtime.sort(key=lambda x: x[1])
    
    print(f"\n🗑️  Arquivos que serão removidos (mais antigos):")
    for i, (file, mtime) in enumerate(files_with_mtime[:to_remove]):
        print(f"   {i+1}. {file.name}")
    
    # Confirmar
    response = input(f"\n❓ Deseja remover {to_remove} arquivos? (s/N): ")
    if response.lower() != 's':
        print("❌ Operação cancelada")
        return
    
    # Remover arquivos
    removed = 0
    for file, _ in files_with_mtime[:to_remove]:
        try:
            file.unlink()
            removed += 1
            print(f"   ✓ Removido: {file.name}")
        except Exception as e:
            print(f"   ✗ Erro ao remover {file.name}: {e}")
    
    print(f"\n✅ Limpeza concluída: {removed} arquivos removidos")
    print(f"📊 Arquivos restantes: {len(list(data_dir.glob('*.txt')))}")

if __name__ == "__main__":
    print("=" * 60)
    print("🧹 LIMPEZA DE ARQUIVOS ÓRFÃOS DE ATIVOS")
    print("=" * 60)
    cleanup_orphan_actives()
