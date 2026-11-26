from dataclasses import asdict, dataclass, field


FATAL = 'fatal'
WARNING = 'warning'


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str  # FATAL or WARNING
    message: str
    source: str    # preflight, xsd, schematron, sk, or a provider name
    location: str = ''

    @property
    def is_fatal(self):
        return self.severity == FATAL


@dataclass
class ValidationReport:
    findings: list = field(default_factory=list)

    @property
    def errors(self):
        return [finding for finding in self.findings if finding.is_fatal]

    @property
    def warnings(self):
        return [finding for finding in self.findings if not finding.is_fatal]

    @property
    def is_valid(self):
        return not self.errors

    def add(self, rule_id, message, source, severity=FATAL, location=''):
        self.findings.append(Finding(rule_id, severity, message, source, location))

    def extend(self, other):
        self.findings.extend(other.findings)
        return self

    def as_dict(self):
        return {'valid': self.is_valid, 'findings': [asdict(finding) for finding in self.findings]}

    def __str__(self):
        return '\n'.join(f'[{f.severity}] {f.rule_id}: {f.message}' for f in self.findings) or 'valid'
