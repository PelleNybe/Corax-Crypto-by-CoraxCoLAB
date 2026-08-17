name: Bug Report
description: Report a bug or issue
title: "[BUG] "
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: |
        Thank you for reporting a bug! Please fill out the following information to help us resolve the issue.
  
  - type: textarea
    id: description
    attributes:
      label: Description
      description: A clear and concise description of what the bug is
      placeholder: Describe the bug...
    validations:
      required: true
  
  - type: textarea
    id: reproduce
    attributes:
      label: Steps to Reproduce
      description: Steps to reproduce the behavior
      placeholder: |
        1. Run...
        2. Do...
        3. See error...
    validations:
      required: true
  
  - type: textarea
    id: expected
    attributes:
      label: Expected Behavior
      description: What should happen instead?
    validations:
      required: true
  
  - type: textarea
    id: environment
    attributes:
      label: Environment
      description: |
        - Python version: (output of `python --version`)
        - Poetry version: (output of `poetry --version`)
        - OS: (Windows/Mac/Linux)
      placeholder: |
        - Python version: 3.12.0
        - Poetry version: 2.4.1
        - OS: Linux
    validations:
      required: true
  
  - type: textarea
    id: logs
    attributes:
      label: Error Logs
      description: Please paste any relevant error messages or logs
      render: bash
  
  - type: checkboxes
    id: confirmation
    attributes:
      label: Confirmation
      options:
        - label: I have searched existing issues
          required: true
        - label: I am using the latest version
          required: true
