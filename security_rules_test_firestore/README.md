# Quanta Digital Twin — Firestore Security Rules Unit Tests

This directory contains automated unit tests for `firestore.rules` using the official `@firebase/rules-unit-testing` framework.

## Prerequisites
1. Node.js (v18+)
2. Firebase CLI (`npm install -g firebase-tools`)
3. Java (required by Firebase Local Emulator Suite)

## Running the Unit Tests Locally

1. Install test dependencies:
   ```bash
   cd security_rules_test_firestore
   npm install
   ```

2. Run tests with the Firebase Local Emulator Suite:
   ```bash
   firebase emulators:exec --only firestore "npm test"
   ```

## Test Coverage Summary
- **User Profiles**: Verified user isolation, profile creation, and rejection of cross-user snooping.
- **Financial Data**: Validated ownership enforcement, positive amount checks, and cross-user update denial.
- **Productivity Data**: Enforced positive session durations and user ownership.
- **Activity History**: Tested immutable audit trail enforcement (creations allowed, updates and deletes blocked).
- **Default Deny**: Verified complete access denial on unlisted collections.
