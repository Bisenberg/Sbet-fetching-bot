import re

def parse_mock_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the first match number (sequence of digits)
    match = re.search(r'(\d+)', content)
    if not match:
        return []
    start = match.start(1)
    content = content[start:]
    print(f'Content after removing leading text: {content[:100]}...')  # Print first 100 chars for verification
    content = content.split('\n\n')  # Split by double newlines to separate blocks
    return content

if __name__ == '__main__':
    blocks = parse_mock_file('/home/toma/Codeprojects/SbetFetch/mock.txt')
    print(f'Hello')
    print(f'Parsed blocks: {blocks}')