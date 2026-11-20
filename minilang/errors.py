"""Error types shared by every stage of the pipeline."""


class MiniLangError(Exception):
    """Base class. `kind` is the label shown to the user (e.g. 'Lexical')."""

    kind = "Compile"

    def __init__(self, message, line=None, col=None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col

    def __str__(self):
        loc = ""
        if self.line is not None:
            loc = f" at line {self.line}"
            if self.col is not None:
                loc += f", column {self.col}"
        return f"{self.kind} Error: {self.message}{loc}."


class LexicalError(MiniLangError):
    kind = "Lexical"


class ParseError(MiniLangError):
    kind = "Syntax"


class SemanticError(MiniLangError):
    kind = "Semantic"


class VMRuntimeError(MiniLangError):
    kind = "Runtime"
