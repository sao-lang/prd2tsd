## 项目背景

{{ project_name }} 是一个 {{ domain }} 领域的技术方案项目。

### 项目目标

{{ summary }}

### 核心需求

{% for req in requirements %}
- **{{ req.id }}** [{{ req.priority }}]: {{ req.description }}
{% endfor %}

### 约束条件

{% for constraint in constraints %}
- [{{ constraint.severity }}] {{ constraint.description }}
{% endfor %}
