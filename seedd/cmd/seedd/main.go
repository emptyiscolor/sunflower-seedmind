package main

import (
	"BugBuster/SeedD/internal/logging"
	"BugBuster/SeedD/internal/server"
	"context"
	"flag"
	"log"

	"go.uber.org/zap"
)

func main() {
	debug := flag.Bool("debug", false, "Enable debug logging")
	flag.Parse()

	// Initialize logger
	if err := logging.InitLogger(*debug); err != nil {
		log.Fatalf("Failed to initialize logger: %v", err)
	}
	defer logging.Sync()

	logger := logging.Logger

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	logger.Info("Starting SeedD server")
	if err := server.Serve(ctx); err != nil {
		logger.Fatal("Server failed", zap.Error(err))
	}
}
