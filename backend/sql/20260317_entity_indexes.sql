-- Indexes for entity consistency lookup performance
create index if not exists idx_entities_entity_type on public.entities(entity_type);
create index if not exists idx_entities_value on public.entities(value);
