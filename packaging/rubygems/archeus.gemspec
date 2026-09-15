# A pointer gem: archeus is a Python program, and this exists so the name on
# RubyGems resolves to the real project rather than to nothing.
Gem::Specification.new do |s|
  s.name        = 'archeus'
  s.version     = '2.4.0'
  s.licenses    = ['MIT']
  s.summary     = 'Pointer gem: archeus is a Python tool — install it with `pipx install archeus`.'
  s.description = 'The memory and workspace layer for AI coding agents: ' \
                  'persistent per-project memory, every session you have ever ' \
                  'had, and control over what the next one costs. Written in ' \
                  'Python; install it with pipx or pip.'
  s.authors     = ['Babar Muhammad Anas']
  s.homepage    = 'https://github.com/babarmuhammad/archeus'
  s.metadata    = {
    'source_code_uri' => 'https://github.com/babarmuhammad/archeus',
    'bug_tracker_uri' => 'https://github.com/babarmuhammad/archeus/issues'
  }
  s.files       = ['bin/archeus', 'README.md']
  s.executables = ['archeus']
  s.bindir      = 'bin'
  s.required_ruby_version = '>= 2.7'
end
