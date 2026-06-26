package aiclient

import (
	"context"
)

type Provider interface {
	Name() string
	Analyze(ctx context.Context, path, prompt string) (*AIResult, error)
}
