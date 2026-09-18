import 'package:flutter/material.dart';

enum FaceGuideShape { oval, roundedRect, none }

/// Colours and geometry of the default overlay. Every value has a sensible
/// default so `const FaceVerifyTheme()` works; pass only what you change.
@immutable
class FaceVerifyTheme {
  const FaceVerifyTheme({
    this.backgroundColor = Colors.black,
    this.maskColor = const Color(0x8C000000),
    this.guideColor = Colors.white,
    this.guideActiveColor = Colors.amber,
    this.guideSuccessColor = Colors.green,
    this.guideFailedColor = Colors.red,
    this.guideShape = FaceGuideShape.oval,
    this.guideWidthFraction = 0.72,
    this.guideAspectRatio = 1.35,
    this.guideCenterY = 0.42,
    this.guideStrokeWidth = 4,
    this.progressColor = Colors.white,
    this.progressBackgroundColor = Colors.white24,
    this.messageStyle = const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w600),
    this.messagePadding = const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
    this.showProgress = true,
    this.showButtons = true,
    this.debugBoxColor = Colors.cyan,
  });

  final Color backgroundColor;
  final Color maskColor;
  final Color guideColor;
  final Color guideActiveColor;
  final Color guideSuccessColor;
  final Color guideFailedColor;
  final FaceGuideShape guideShape;
  final double guideWidthFraction;
  final double guideAspectRatio;
  final double guideCenterY;
  final double guideStrokeWidth;
  final Color progressColor;
  final Color progressBackgroundColor;
  final TextStyle messageStyle;
  final EdgeInsets messagePadding;
  final bool showProgress;
  final bool showButtons;
  final Color debugBoxColor;

  /// Derives guide colours from a [ColorScheme] so the overlay follows the app theme.
  factory FaceVerifyTheme.fromScheme(ColorScheme scheme) => FaceVerifyTheme(
        guideColor: scheme.onSurface,
        guideActiveColor: scheme.primary,
        guideSuccessColor: scheme.tertiary,
        guideFailedColor: scheme.error,
        progressColor: scheme.primary,
        messageStyle: TextStyle(color: scheme.onSurface, fontSize: 22, fontWeight: FontWeight.w600),
      );

  FaceVerifyTheme copyWith({
    Color? backgroundColor,
    Color? maskColor,
    Color? guideColor,
    Color? guideActiveColor,
    Color? guideSuccessColor,
    Color? guideFailedColor,
    FaceGuideShape? guideShape,
    double? guideWidthFraction,
    double? guideAspectRatio,
    double? guideCenterY,
    double? guideStrokeWidth,
    Color? progressColor,
    Color? progressBackgroundColor,
    TextStyle? messageStyle,
    EdgeInsets? messagePadding,
    bool? showProgress,
    bool? showButtons,
    Color? debugBoxColor,
  }) =>
      FaceVerifyTheme(
        backgroundColor: backgroundColor ?? this.backgroundColor,
        maskColor: maskColor ?? this.maskColor,
        guideColor: guideColor ?? this.guideColor,
        guideActiveColor: guideActiveColor ?? this.guideActiveColor,
        guideSuccessColor: guideSuccessColor ?? this.guideSuccessColor,
        guideFailedColor: guideFailedColor ?? this.guideFailedColor,
        guideShape: guideShape ?? this.guideShape,
        guideWidthFraction: guideWidthFraction ?? this.guideWidthFraction,
        guideAspectRatio: guideAspectRatio ?? this.guideAspectRatio,
        guideCenterY: guideCenterY ?? this.guideCenterY,
        guideStrokeWidth: guideStrokeWidth ?? this.guideStrokeWidth,
        progressColor: progressColor ?? this.progressColor,
        progressBackgroundColor: progressBackgroundColor ?? this.progressBackgroundColor,
        messageStyle: messageStyle ?? this.messageStyle,
        messagePadding: messagePadding ?? this.messagePadding,
        showProgress: showProgress ?? this.showProgress,
        showButtons: showButtons ?? this.showButtons,
        debugBoxColor: debugBoxColor ?? this.debugBoxColor,
      );
}
