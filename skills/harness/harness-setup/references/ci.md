# Harness Setup Reference: ci

This file is part of `references/` for `harness-setup`.

### ci — CI/CD 設定

GitHub Actions ワークフローを設定する。

```yaml
# .github/workflows/ci.yml 生成例
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm test
```

