import re

def parse_mock_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    match = re.search(r'(\d+)', content)
    if not match:
        return []
    start = match.start(1)
    content = content[start:]
    print(f'Content after removing leading text: {content[:100]}...')  
    content = content.split('\n\n') 
    return content

if __name__ == '__main__':
    blocks = parse_mock_file('/home/toma/Codeprojects/SbetFetch/mock.txt')
    print(f'Hello')
    print(f'Parsed blocks: {blocks}')