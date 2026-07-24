## 总体架构

### 架构模式

采用 **{{ architecture_pattern }}** 架构模式。

### 架构图

```mermaid
{{ component_diagram }}
```

### 组件说明

{% for comp in components %}
#### {{ comp.name }}

- **类型**: {{ comp.type }}
- **职责**: {{ comp.responsibility }}
- **关键功能**:
{% for func in comp.key_functions %}
  - {{ func }}
{% endfor %}
- **依赖**: {{ comp.dependencies | join(', ') }}

{% endfor %}
