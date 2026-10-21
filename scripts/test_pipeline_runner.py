import sys, os, json
from pathlib import Path

m4_src = Path('member4/SFIC_Doc_Module/src').resolve()
sys.path.insert(0, str(m4_src))

os.environ['GROQ_API_KEY'] = os.getenv('GROQ_API_KEY', '')
os.environ['LLM_PROVIDER'] = 'groq'
os.environ['LLM_MODEL'] = 'openai/gpt-oss-120b'

from atlas.pipeline.runner import PipelineRunner
from atlas.config import get_settings

settings = get_settings()
print('Running PipelineRunner with Groq on FIR_CASE_003.pdf...')
runner = PipelineRunner(settings=settings)

pdf_path = Path(r'C:\Users\suraj\Downloads\Updated dataset\CASE_003\FIR_CASE_003.pdf')
result = runner.run(
    case_id='CASE_003_TEST',
    file_paths=[pdf_path],
    provider='groq',
    model_version='openai/gpt-oss-120b'
)

print('State:', result.state)
print('Mentions count:', len(result.mentions))
for m in result.mentions:
    q = m.source.quote if m.source else 'None'
    print(f' - [{m.type}] {m.surface_text} (canon: {m.normalized_value}, role: {m.stated_role}, trust: {m.identifier_trust})')
    print(f'     quote: \"{q}\"')

print('Relationships count:', len(result.relationships))
for r in result.relationships:
    q = r.source.quote if r.source else 'None'
    print(f' - {r.type}: {r.subject_mention_id} -> {r.object_mention_id} (quote: \"{q}\")')

print('Events count:', len(result.events))
for ev in result.events:
    t_str = ev.time.normalized_iso if ev.time else 'None'
    print(f' - [{ev.type}] {t_str}: {ev.description}')

print('Aggregates:', result.aggregates)
print('Review items:', len(result.review_items))
for ri in result.review_items:
    print(f' - [{ri.kind}] {ri.detail}')
