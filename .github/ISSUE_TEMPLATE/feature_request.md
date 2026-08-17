name: Feature Request
description: Suggest a new feature
title: "[FEATURE] "
labels: ["enhancement"]
body:
  - type: markdown
    attributes:
      value: |
        Thank you for suggesting a feature! Please provide details about your feature request.
  
  - type: textarea
    id: description
    attributes:
      label: Feature Description
      description: A clear and concise description of what the feature should do
      placeholder: Describe the feature...
    validations:
      required: true
  
  - type: textarea
    id: motivation
    attributes:
      label: Motivation
      description: Why should this feature be implemented? What problem does it solve?
    validations:
      required: true
  
  - type: textarea
    id: implementation
    attributes:
      label: Suggested Implementation
      description: Describe how this feature could be implemented (optional)
      placeholder: Describe the approach...
  
  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives Considered
      description: What alternatives have you considered?
  
  - type: checkboxes
    id: confirmation
    attributes:
      label: Confirmation
      options:
        - label: I have searched existing feature requests
          required: true
