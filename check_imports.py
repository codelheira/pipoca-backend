import os
import re

def check_optional_imports(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                    # Se 'Optional' aparece como tipo (ex: Optional[str]) ou valor padrão, mas não no import
                    if 'Optional' in content:
                        has_import = re.search(r'from typing import .*Optional', content)
                        if not has_import:
                            print(f"Missing Optional import in: {path}")

if __name__ == "__main__":
    check_optional_imports(r'c:\Users\Sirac\Documents\Projetos\pipoca-backend\app')
