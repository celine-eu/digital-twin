# Create a Digital Twin Module (Developer Guide)

This guide is an **actionable, end‑to‑end introduction** for developers who want to
add new functionality to the CELINE Digital Twin runtime.

By the end of this guide, you will have:
- created a new DT module
- implemented a runnable DT app
- exposed it via the API
- defined module-scoped value fetchers
- verified it locally

No prior knowledge of CELINE internals is required.

---

## Module conceptual model

Before writing code, familiarize with these **three rules**:

1. **A module is a packaging unit**
   - it groups one or more apps
   - it can define value fetchers
   - it has no runtime logic by itself

2. **An app is the executable unit**
   - it contains domain logic only
   - it does NOT know about HTTP, FastAPI, or SQLAlchemy

3. **All infrastructure is injected**
   - datasets, state, tokens, services come via `RunContext`
   - this keeps apps testable and portable

---

## 1. Create the module structure

Create a new directory eg. `my_module`:

```
my_module/hello_world/
├── __init__.py   # empty file for python module lookup
├── app.py        # domain logic
├── models.py     # input/output models
├── mappers.py    # external API contract
└── module.py     # module registration
```

---

## 2. Define input and output models

Use **Pydantic models** to define the public contract of your app.

```python
# models.py
from pydantic import BaseModel, Field


class HelloWorldConfig(BaseModel):
    name: str = Field(..., description="Name to greet")


class HelloWorldResult(BaseModel):
    message: str
```

These models:
- define validation rules
- generate JSON Schemas automatically
- are exposed via `/apps/<app>/describe`

---

## 3. Implement the app logic

Apps contain **only domain logic**.

```python
# app.py
from celine.dt.contracts.app import DTApp
from celine.dt.core.context import RunContext

from .models import HelloWorldConfig, HelloWorldResult


class HelloWorldApp(DTApp[HelloWorldConfig, HelloWorldResult]):
    key = "hello-world"
    version = "1.0.0"

    config_type = HelloWorldConfig
    result_type = HelloWorldResult

    input_mapper = None
    output_mapper = None

    async def run(
        self,
        config: HelloWorldConfig,
        context: RunContext,
    ) -> HelloWorldResult:
        return HelloWorldResult(
            message=f"Hello {config.name}!"
        )
```

Key points:
- `run()` is async
- no HTTP, no database access here
- everything external must come from `context`

---

## 4. (Optional) Add mappers

Mappers control how your app appears externally.

You need them if:
- you want camelCase output
- you want to reshape inputs
- you want strict API compatibility

```python
# mappers.py
from typing import Mapping
from celine.dt.contracts.mapper import InputMapper, OutputMapper

from .models import HelloWorldConfig, HelloWorldResult


class HelloWorldInputMapper(InputMapper[HelloWorldConfig]):
    input_type = HelloWorldConfig

    def map(self, raw: Mapping) -> HelloWorldConfig:
        return HelloWorldConfig.model_validate(raw)


class HelloWorldOutputMapper(OutputMapper[HelloWorldResult]):
    output_type = HelloWorldResult

    def map(self, result: HelloWorldResult) -> dict:
        return {
            "message": result.message
        }
```

Then wire them into the app:

```python
input_mapper = HelloWorldInputMapper()
output_mapper = HelloWorldOutputMapper()
```

---

## 5. Register the module

Modules are responsible for **registering apps**.

```python
# module.py
from celine.dt.core.registry import DTRegistry
from .app import HelloWorldApp


class HelloWorldModule:
    name = "hello-world"
    version = "1.0.0"

    def register(self, registry: DTRegistry) -> None:
        registry.register_app(HelloWorldApp())


module = HelloWorldModule()
```

Nothing else should happen in a module.

---

## 6. Enable the module

Add the module to your configuration file:

```yaml
# config/modules.yaml
modules:
  - name: hello-world
    version: ">=1.0.0"
    import: celine.dt.modules.hello_world.module:module
    enabled: true
```

Restart the core DT runtime.

---

## 7. Verify via API

List available apps:

```bash
curl http://localhost:8000/apps
```

Check your app description:

```bash
curl http://localhost:8000/apps/hello-world/describe
```

Run your app:

```bash
curl -X POST http://localhost:8000/apps/hello-world/run \
  -H "Content-Type: application/json" \
  -d '{ "name": "CELINE" }'
```

Expected response:

```json
{
  "message": "Hello CELINE!"
}
```

---

## 8. Testing your app (recommended)

Because apps are pure, testing is trivial:

```python
import asyncio
from celine.dt.core.runner import DTAppRunner
from celine.dt.core.registry import DTRegistry
from celine.dt.core.context import RunContext

from celine.dt.modules.hello_world.app import HelloWorldApp


def test_hello_world_app():
    registry = DTRegistry()
    registry.register_app(HelloWorldApp())

    runner = DTAppRunner()

    result = asyncio.run(
        runner.run(
            registry=registry,
            app_key="hello-world",
            payload={"name": "Test"},
            context=RunContext.create(
                datasets=None,
                state=None,
                token_provider=None,
            ),
        )
    )

    assert result.message == "Hello Test!"
```

---

## 9. Adding module-scoped value fetchers

Modules can define **value fetchers** that are namespaced under the module name.

Add a `values` section to your module configuration:

```yaml
# config/modules.yaml
modules:
  - name: hello-world
    version: ">=1.0.0"
    import: celine.dt.modules.hello_world.module:module
    enabled: true
    values:
      greetings:
        client: dataset_api
        query: |
          SELECT * FROM greetings
          WHERE language = :language
        limit: 100
        payload:
          type: object
          required: [language]
          properties:
            language:
              type: string
              default: en
```

This fetcher will be accessible as `hello-world.greetings`:

```bash
# List fetchers
curl http://localhost:8000/values

# Fetch data
curl "http://localhost:8000/values/hello-world.greetings?language=it"
```

### When to use module values vs global values

| Use case | Location |
|----------|----------|
| Module-specific data needs | Module config (`values:` section) |
| Cross-cutting data access | Global `config/values.yaml` |
| Shared reference data | Global `config/values.yaml` |

---

## 10. Using data in your app

Apps can query data via the `context.datasets` client:

```python
async def run(
    self,
    config: MyConfig,
    context: RunContext,
) -> MyResult:
    # Query data
    rows = await context.datasets.query(
        sql=f"SELECT * FROM table WHERE id = {config.id}",
        limit=100,
    )
    
    # Process and return
    return MyResult(data=rows)
```

For reusable, declarative data access, prefer **value fetchers** over hardcoded queries.

---

## Common mistakes

- putting database logic inside apps
- importing FastAPI inside apps
- hardcoding dataset or environment details
- testing apps via HTTP only
- defining value fetchers with hardcoded parameters

If you avoid these, your module will stay clean and maintainable.

---

## Next steps

- Explore the `ev_charging` module for a realistic example
- Add dataset queries via `context.datasets.query(sql=...)`
- Define value fetchers for reusable data access
- Introduce state via `context.state` if needed
- See [Values API](values.md) for detailed fetcher configuration

You are now ready to build real Digital Twin capabilities.