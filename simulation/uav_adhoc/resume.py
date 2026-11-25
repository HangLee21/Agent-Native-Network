from pathlib import Path
p=Path('coordination/tasks/E1-030.md');s=p.read_text(encoding='utf-8-sig').replace('状态：review（部分交付，实验尚未完成）','状态：running（M-036 Wi-Fi接续）',1);p.write_text(s,encoding='utf-8')
