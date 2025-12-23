# Create a new DT module

This guide explains how to create a **new Digital Twin module** from a developer
perspective.

---

## 1. Create the module structure

```
celine/dt/modules/my_module/
├── app.py
├── models.py
├── mappers.py
└── module.py
```

---

## 2. Define input and output models

Use Pydantic models to define the app contract.

```python
class MyInputs(BaseModel):
    ...

class MyResult(BaseModel):
    ...
```

---

## 3. Implement the app

```python
class MyApp:
    key = "my-app"
    version = "1.0.0"

    async def run(self, inputs: MyInputs, context: RunContext) -> MyResult:
        ...
```

The app contains **only domain logic**.

---

## 4. Implement mappers

```python
class MyInputMapper(InputMapper[MyInputs]):
    def map(self, raw: Mapping) -> MyInputs:
        ...

class MyOutputMapper(OutputMapper[MyResult]):
    def map(self, obj: MyResult) -> dict:
        ...
```

Mappers define the **external contract**.

---

## 5. Register the module

```python
class MyModule:
    name = "my-module"
    version = "1.0.0"

    def register(self, registry: DTRegistry) -> None:
        registry.register_app(
            MyApp(),
            input_mapper=MyInputMapper(),
            output_mapper=MyOutputMapper(),
        )

module = MyModule()
```

---

## 6. Enable the module

Add the module to `config/modules.yaml`:

```yaml
modules:
  - name: my-module
    import: celine.dt.modules.my_module.module:module
    enabled: true
```

---

## 7. Verify

```bash
curl http://localhost:8000/apps
curl http://localhost:8000/apps/my-app/describe
```

Your module is now part of the Digital Twin runtime.
