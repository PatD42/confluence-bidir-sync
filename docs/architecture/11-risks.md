# Architecture - Risks & Technical Debt

---

## Known Risks

### Risk 1: Macro Compatibility Gaps

**Description**: Not all Confluence macros may survive the surgical update process perfectly.

**Likelihood**: Medium
**Impact**: Medium

**Affected Components**: SurgicalEditor, PageOperations

**Mitigation Strategies**:
1. Surgical updates never modify `ac:` elements (current approach)
2. Macro count verification before/after operations
3. E2E tests for common macro types (toc, info, warning, code)
4. Document unsupported macro edge cases

**Status**: Mitigated - surgical approach preserves macros by never touching them

**Monitoring**: E2E test suite validates macro preservation

---

### Risk 2: Confluence API Changes

**Description**: Atlassian may change REST API v2, breaking compatibility.

**Likelihood**: Low
**Impact**: High

**Affected Components**: APIWrapper, all API interactions

**Mitigation Strategies**:
1. Pin atlassian-python-api version
2. Contract tests to detect API changes (planned)
3. Monitor Atlassian developer changelog
4. Abstract API interactions behind wrapper

**Status**: Partially mitigated via version pinning

**Monitoring**: Contract tests (planned), manual changelog review

---

### Risk 3: Pandoc Dependency

**Description**: External tool dependency may cause installation or compatibility issues.

**Likelihood**: Low
**Impact**: Medium

**Affected Components**: MarkdownConverter

**Mitigation Strategies**:
1. Document minimum Pandoc version (3.8.3+)
2. Clear error message if Pandoc not found
3. Version check on startup (planned)
4. Consider bundled Pandoc or alternative converter (future)

**Status**: Accepted risk with documentation

**Monitoring**: User feedback, installation success rate

---

### Risk 4: Rate Limit Exhaustion

**Description**: Bulk operations may exhaust Confluence rate limits beyond retry capacity.

**Likelihood**: Low
**Impact**: Medium

**Affected Components**: APIWrapper, retry_logic

**Mitigation Strategies**:
1. Exponential backoff (1s, 2s, 4s)
2. Respect Retry-After header
3. Future: Configurable delay between operations
4. Future: Bulk operation pacing

**Status**: Mitigated for typical use cases

**Monitoring**: API error counts in logs

---

## Technical Debt

### TD-1: Version Conflict Test Skipped

**Description**: E2E test for version conflict handling is skipped because atlassian-python-api auto-manages versions.

**Impact**: Low - unit tests cover the logic

**Remediation**: Find way to test via API or accept as known limitation

**Priority**: Low

---

### TD-2: Test Coverage Below 90%

**Description**: Current coverage is 87%, below ideal 90% target.

**Impact**: Low - core paths covered

**Remediation**: Add tests for edge cases, error paths

**Priority**: Low

---

### TD-3: No Integration Test Layer

**Description**: Tests jump from unit (mocked) to E2E (real Confluence). Missing middle layer.

**Impact**: Medium - some integration bugs may slip through

**Remediation**: Add integration tests with real Pandoc, mocked Confluence

**Priority**: Medium (planned)

---

### TD-4: Legacy ARCHITECTURE.md

**Description**: Original `ARCHITECTURE.md` exists alongside new Arc42 structure.

**Impact**: Low - documentation duplication

**Remediation**: Migrate unique content to Arc42 docs, archive or delete original

**Priority**: Low

---

### TD-5: No CI/CD Pipeline

**Description**: Tests run locally only; no automated CI/CD.

**Impact**: Medium - manual testing burden

**Remediation**: Add GitHub Actions workflow (see deployment view)

**Priority**: Medium (planned)

---

## Risk Matrix

| Risk | Likelihood | Impact | Priority |
|------|------------|--------|----------|
| Macro compatibility gaps | Medium | Medium | High |
| Confluence API changes | Low | High | Medium |
| Pandoc dependency | Low | Medium | Low |
| Rate limit exhaustion | Low | Medium | Low |

## Technical Debt Matrix

| Debt | Impact | Effort | Priority |
|------|--------|--------|----------|
| TD-1: Skipped test | Low | High | Low |
| TD-2: Coverage <90% | Low | Medium | Low |
| TD-3: No integration tests | Medium | Medium | Medium |
| TD-4: Legacy docs | Low | Low | Low |
| TD-5: No CI/CD | Medium | Medium | Medium |

---
