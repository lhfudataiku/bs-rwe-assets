<div class="alert">
Internal use only: SYNPUF licence restriction. Do not install on customer instances.
</div>

# Instance Requirements
This project is compatible with instances with **Dataiku V13.4+**.

# Connections
{{connections}}

# Schema contract
Every table in the `OMOP CDM export` zone must pass the solution's v1.1 schema check (`CDM_SCHEMA` at
`v1-1-1`). Keep column names lowercase: the solution uppercases them on import (DEC-RWD-001).
